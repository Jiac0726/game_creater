from __future__ import annotations

from app.completion_models import AssetCompletionRequest
from app.models import BBox
from app.services.completion_service import CompletionService
from app.services.pipeline import AssetSplitPipeline
from app.services.workflow_manager import WorkflowManager
from app.workflow_models import RunProjectRequest, WorkflowStage


def test_mock_project_workflow_runs_semantics_generation_and_split(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GAME_CREATER_MODE", "mock")
    pipeline = AssetSplitPipeline(tmp_path / "workspace")
    manager = WorkflowManager(tmp_path / "workspace", pipeline)

    project = manager.run(
        RunProjectRequest(
            concept="废弃地铁站",
            provider="mock",
            size="800x450",
            quality="medium",
            auto_split=True,
        )
    )

    assert project.stage == WorkflowStage.ASSET_REVIEW
    assert project.asset_plan is not None
    assert project.asset_plan.assets
    assert project.asset_plan.detection_prompts
    assert project.generation is not None
    assert project.generation.provider == "mock"
    assert project.scene_id

    project_dir = manager.store.project_dir(project.project_id)
    assert (project_dir / "project.json").is_file()
    assert (project_dir / "semantic" / "plan.json").is_file()
    assert (project_dir / "generation" / "request.json").is_file()
    assert (project_dir / "generation" / "metadata.json").is_file()
    assert (project_dir / "generation" / "source.png").is_file()

    scene_dir = tmp_path / "workspace" / project.scene_id
    assert (scene_dir / "scene.json").is_file()
    assert any(event.stage == WorkflowStage.GENERATING for event in project.events)
    assert any(event.stage == WorkflowStage.ASSET_REVIEW for event in project.events)


def test_project_workflow_can_stop_after_generation(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GAME_CREATER_MODE", "mock")
    pipeline = AssetSplitPipeline(tmp_path / "workspace")
    manager = WorkflowManager(tmp_path / "workspace", pipeline)

    project = manager.run(
        RunProjectRequest(
            concept="魔法森林",
            provider="mock",
            size="512x512",
            auto_split=False,
        )
    )

    assert project.stage == WorkflowStage.IMAGE_READY
    assert project.scene_id is None
    assert project.generation is not None


def test_completion_result_is_recorded_back_into_project_history(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GAME_CREATER_MODE", "mock")
    workspace = tmp_path / "workspace"
    pipeline = AssetSplitPipeline(workspace)
    manager = WorkflowManager(workspace, pipeline)

    project = manager.run(
        RunProjectRequest(
            concept="废弃地铁站",
            provider="mock",
            size="640x360",
            auto_split=True,
        )
    )
    assert project.scene_id

    scene = manager.pipeline.workspace / project.scene_id / "scene.json"
    assert scene.is_file()
    manifest = manager.pipeline.run.__self__  # keep pipeline object explicitly referenced for clarity
    del manifest

    from app.services.scene_store import SceneStore

    scene_manifest = SceneStore(workspace).load(project.scene_id)
    asset = scene_manifest.assets[0]
    rect = BBox(
        x1=asset.bbox.x1,
        y1=asset.bbox.y1,
        x2=asset.bbox.x2,
        y2=max(asset.bbox.y1 + 1, min(asset.bbox.y2, asset.bbox.y1 + max(2, (asset.bbox.y2 - asset.bbox.y1) // 4))),
    )

    result = CompletionService(workspace, pipeline).complete(
        project.scene_id,
        asset.id,
        AssetCompletionRequest(rect=rect, provider="mock"),
    )
    updated = manager.record_completion(result)

    assert updated is not None
    assert updated.project_id == project.project_id
    assert updated.stage == WorkflowStage.ASSET_REVIEW
    assert len(updated.completion_jobs) == 1
    job = updated.completion_jobs[0]
    assert job.id == result.job_id
    assert job.asset_id == asset.id
    assert job.status == "completed"
    assert job.output_asset == result.completed_asset
    assert any(event.stage == WorkflowStage.COMPLETING for event in updated.events)
    assert updated.events[-1].stage == WorkflowStage.ASSET_REVIEW
