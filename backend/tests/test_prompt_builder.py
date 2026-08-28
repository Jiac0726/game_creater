from __future__ import annotations

from app.services.prompt_builder import PromptBuilder
from app.services.semantic_engine import SemanticEngine


def test_prompt_builder_creates_asset_plan_and_split_friendly_scene_prompt() -> None:
    expansion = SemanticEngine().expand("废弃地铁站", depth=2, max_per_group=12)
    builder = PromptBuilder()
    plan = builder.build_plan(expansion)
    prompt = builder.build_generation_prompt(plan)

    assert plan.concept == "废弃地铁站"
    assert plan.assets
    assert plan.detection_prompts
    assert any(asset.group == "props" for asset in plan.assets)
    assert "downstream game-asset extraction" in prompt
    assert "Reduce heavy occlusion" in prompt
    assert "Do not create a contact sheet" in prompt
