from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from app.completion_models import AssetCompletionResult
from app.services.asset_library import AssetLibrary
from app.services.generation_providers import (
    ImageGenerationError,
    ImageGenerationProviderRegistry,
)
from app.services.pipeline import AssetSplitPipeline
from app.services.project_store import ProjectStore
from app.services.prompt_builder import PromptBuilder
from app.services.scene_store import SceneStore
from app.services.semantic_engine import SemanticEngine
from app.workflow_models import (
    CompletionJob,
    GenerationSpec,
    ProjectRecord,
    RunProjectRequest,
    WorkflowStage,
)


class WorkflowManager:
    """Synchronous orchestration for the first end-to-end production workflow."""

    def __init__(self, workspace: str | Path, pipeline: AssetSplitPipeline) -> None:
        self.workspace = Path(workspace)
        self.store = ProjectStore(self.workspace)
        self.scene_store = SceneStore(self.workspace)
        self.asset_library = AssetLibrary(self.workspace)
        self.semantic = SemanticEngine()
        self.prompt_builder = PromptBuilder()
        self.providers = ImageGenerationProviderRegistry()
        self.pipeline = pipeline

    def run(self, request: RunProjectRequest) -> ProjectRecord:
        concept = request.concept.strip()
        if not concept:
            raise ValueError("Project concept cannot be empty")

        project_id = uuid4().hex[:12]
        record = self.store.create(project_id, concept)
        try:
            self.store.event(record, WorkflowStage.SEMANTIC_PLANNING, "Expanding game-asset semantics")
            expansion = self.semantic.expand(
                concept,
                depth=request.semantic_depth,
                max_per_group=request.max_per_group,
            )
            plan = self.prompt_builder.build_plan(expansion)
            record.asset_plan = plan

            project_dir = self.store.project_dir(project_id)
            semantic_dir = project_dir / "semantic"
            semantic_dir.mkdir(parents=True, exist_ok=True)
            (semantic_dir / "plan.json").write_text(
                json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            prompt = self.prompt_builder.build_generation_prompt(plan)
            negative_prompt = self.prompt_builder.build_negative_prompt()
            spec = GenerationSpec(
                provider=request.provider,
                model=request.model,
                size=request.size,
                quality=request.quality,
                prompt=prompt,
                negative_prompt=negative_prompt,
            )
            generation_dir = project_dir / "generation"
            generation_dir.mkdir(parents=True, exist_ok=True)
            (generation_dir / "request.json").write_text(
                json.dumps(spec.model_dump(mode="json"), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.store.event(
                record,
                WorkflowStage.PROMPT_READY,
                "Generation prompt prepared",
                data={"prompt_count": len(plan.detection_prompts)},
            )

            self.store.event(record, WorkflowStage.GENERATING, f"Generating with {request.provider}")
            provider = self.providers.get(request.provider)
            output_path = generation_dir / "source.png"
            generation = provider.generate(spec, output_path)
            generation.image_file = "generation/source.png"
            record.generation = generation
            (generation_dir / "metadata.json").write_text(
                json.dumps(generation.model_dump(mode="json"), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.store.event(
                record,
                WorkflowStage.IMAGE_READY,
                "Generated image saved to project",
                data={"image_file": generation.image_file, "provider": generation.provider},
            )

            if request.auto_split:
                self.store.event(
                    record,
                    WorkflowStage.DETECTING,
                    "Sending generated scene into detection and segmentation",
                )
                manifest = self.pipeline.run(output_path, plan.detection_prompts)
                # Add Project provenance after the generic scene pipeline has
                # already assigned stable global library IDs.
                self.asset_library.sync_scene(manifest, project_id=project_id)
                self.scene_store.save(manifest)
                record.scene_id = manifest.scene_id
                self.store.event(
                    record,
                    WorkflowStage.ASSET_REVIEW,
                    "Generated scene split into reusable assets",
                    data={
                        "scene_id": manifest.scene_id,
                        "asset_count": len(manifest.assets),
                        "planned_asset_count": len(plan.assets),
                        "library_asset_ids": [
                            asset.library_asset_id for asset in manifest.assets if asset.library_asset_id
                        ],
                    },
                )
            else:
                self.store.event(record, WorkflowStage.IMAGE_READY, "Generation complete; auto split disabled")

            return self.store.load(project_id)
        except Exception as exc:
            record.error = str(exc)
            self.store.event(
                record,
                WorkflowStage.FAILED,
                str(exc),
                status="error",
                data={"exception": exc.__class__.__name__},
            )
            if isinstance(exc, (ImageGenerationError, ValueError, RuntimeError)):
                raise
            raise RuntimeError(str(exc)) from exc

    def record_completion(self, result: AssetCompletionResult) -> ProjectRecord | None:
        record = self.store.find_by_scene(result.scene_id)
        if record is None:
            return None

        self.store.event(
            record,
            WorkflowStage.COMPLETING,
            f"Completing asset {result.asset_id} with {result.provider}",
            data={"job_id": result.job_id, "asset_id": result.asset_id},
        )
        record.completion_jobs.append(
            CompletionJob(
                id=result.job_id,
                asset_id=result.asset_id,
                mode=result.mode,
                status="completed",
                provider=result.provider,
                source_asset=result.source_asset,
                output_asset=result.completed_asset,
                metadata={
                    "completed_scene": result.completed_scene,
                    "completed_mask": result.completed_mask,
                    "rect": result.rect.model_dump(),
                    "resegmented": result.resegmented,
                    "confidence": result.confidence,
                },
            )
        )

        scene = self.scene_store.load(result.scene_id)
        source_asset = next((asset for asset in scene.assets if asset.id == result.asset_id), None)
        if source_asset and source_asset.library_asset_id:
            self.asset_library.add_version(
                source_asset.library_asset_id,
                kind="ai_completed",
                image_path=f"{result.scene_id}/{result.completed_asset}",
                mask_path=f"{result.scene_id}/{result.completed_mask}",
                metadata={
                    "completion_job_id": result.job_id,
                    "provider": result.provider,
                    "mode": result.mode,
                    "rect": result.rect.model_dump(),
                    "resegmented": result.resegmented,
                    "confidence": result.confidence,
                    "original_asset_unchanged": True,
                },
                activate=False,
            )

        self.store.event(
            record,
            WorkflowStage.ASSET_REVIEW,
            "Completion result stored for review; original asset preserved",
            data={"job_id": result.job_id, "output_asset": result.completed_asset},
        )
        return self.store.load(record.project_id)

    def load(self, project_id: str) -> ProjectRecord:
        return self.store.load(project_id)

    def provider_catalog(self) -> list[dict]:
        return self.providers.catalog()
