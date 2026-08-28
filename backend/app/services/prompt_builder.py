from __future__ import annotations

from app.models import SemanticExpansion
from app.workflow_models import AssetPlan, PlannedAsset


class PromptBuilder:
    """Turn semantic expansion into a scene-generation plan and split-friendly prompt."""

    GROUP_LABELS = {
        "buildings": "architecture",
        "structures": "structures",
        "props": "props",
        "vegetation": "vegetation",
        "terrain": "terrain",
        "vehicles": "vehicles",
        "creatures": "creatures",
        "effects": "environmental effects",
        "materials": "materials",
    }

    def build_plan(self, expansion: SemanticExpansion) -> AssetPlan:
        assets: list[PlannedAsset] = []
        seen: set[str] = set()
        for group in expansion.groups:
            for item in group.items:
                key = item.en.strip().lower()
                if not key or key in seen:
                    continue
                seen.add(key)
                assets.append(
                    PlannedAsset(
                        zh=item.zh,
                        en=item.en.strip(),
                        group=group.key,
                        score=item.score,
                        source=item.source,
                    )
                )

        return AssetPlan(
            concept=expansion.input,
            matched_concept=expansion.matched_concept_label,
            modifiers=list(expansion.modifiers),
            assets=assets,
            detection_prompts=list(expansion.detection_prompts),
        )

    def build_generation_prompt(self, plan: AssetPlan) -> str:
        by_group: dict[str, list[str]] = {}
        for asset in plan.assets:
            if asset.group in {"effects", "materials"}:
                continue
            bucket = by_group.setdefault(asset.group, [])
            if len(bucket) < 8:
                bucket.append(asset.en)

        sections: list[str] = []
        for group_key, values in by_group.items():
            label = self.GROUP_LABELS.get(group_key, group_key)
            sections.append(f"{label}: {', '.join(values)}")

        modifiers = ", ".join(plan.modifiers) if plan.modifiers else ""
        concept_line = plan.matched_concept or plan.concept
        asset_lines = "; ".join(sections)

        return (
            f"Create a polished 2D game environment concept scene for: {concept_line}. "
            f"User concept: {plan.concept}. "
            + (f"Scene modifiers: {modifiers}. " if modifiers else "")
            + (f"Include clearly recognizable game assets: {asset_lines}. " if asset_lines else "")
            + "Compose the scene specifically for downstream game-asset extraction. "
            "Keep important objects fully visible whenever possible, with clear silhouettes and readable boundaries. "
            "Reduce heavy occlusion between reusable props, avoid fusing neighboring objects together, and leave practical visual separation around important assets. "
            "Use coherent perspective, lighting, scale and art direction so the result still reads as one believable scene. "
            "Do not create a contact sheet, sprite sheet, labeled diagram, UI mockup, collage, or isolated-object grid. "
            "The result must be a single natural game scene that remains friendly to object detection and segmentation."
        )

    @staticmethod
    def build_negative_prompt() -> str:
        return (
            "contact sheet, sprite sheet, object grid, collage, labels, text annotations, UI, watermark, "
            "heavily fused props, excessive occlusion, duplicated objects, malformed geometry, unreadable silhouettes"
        )
