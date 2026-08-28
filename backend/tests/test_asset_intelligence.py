from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from app.asset_intelligence_models import AssetIntelligenceApplyRequest
from app.main import app
from app.services.ai_action_registry import AIActionRegistry
from app.services.asset_intelligence import AssetIntelligenceService
from app.services.asset_library_workflow import AssetLibraryWorkflowService
from app.services.pipeline import AssetSplitPipeline


def _setup(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GAME_CREATER_MODE", "mock")
    workspace = tmp_path / "workspace"
    pipeline = AssetSplitPipeline(workspace)
    return workspace, AssetLibraryWorkflowService(workspace, pipeline)


def _sprite(path: Path, shift: int = 0):
    image = Image.new("RGBA", (96, 128), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((25 + shift, 20, 70 + shift, 118), fill=(40, 140, 60, 255))
    image.save(path)


def test_intelligence_analyzes_without_mutating_then_applies(tmp_path: Path, monkeypatch) -> None:
    workspace, workflow = _setup(tmp_path, monkeypatch)
    path = tmp_path / "tree.png"
    _sprite(path)
    asset = workflow.import_image(path, name="Ancient Tree", category="uncategorized", tags=["keep-me"])
    service = AssetIntelligenceService(workspace)

    report = service.analyze(asset.id)
    before = service.library.get(asset.id)
    assert before.category == "uncategorized"
    assert "keep-me" in before.tags
    assert report.quality_score > 0
    assert report.suggested_category in {"vegetation", "uncategorized"}

    updated = service.apply(asset.id, AssetIntelligenceApplyRequest(report=report))
    assert "keep-me" in updated.tags
    for tag in report.suggested_tags:
        assert tag in updated.tags
    assert updated.category == report.suggested_category


def test_intelligence_detects_visual_duplicates(tmp_path: Path, monkeypatch) -> None:
    workspace, workflow = _setup(tmp_path, monkeypatch)
    a = tmp_path / "tree_a.png"
    b = tmp_path / "tree_b.png"
    _sprite(a)
    _sprite(b)
    first = workflow.import_image(a, name="Tree A", category="vegetation")
    second = workflow.import_image(b, name="Tree B", category="vegetation")
    report = AssetIntelligenceService(workspace).analyze(first.id, duplicate_threshold=0.95)
    assert any(item.asset_id == second.id and item.visual_similarity >= 0.95 for item in report.duplicate_candidates)


def test_asset_intelligence_is_ai_native() -> None:
    actions = {item.action_id for item in AIActionRegistry(app).catalog().actions}
    required = {
        "get.library.intelligence.status",
        "post.library.intelligence.assets.asset_id.analyze",
        "post.library.intelligence.analyze.bulk",
        "post.library.intelligence.assets.asset_id.apply",
    }
    assert required.issubset(actions)
    tools = {item.function["x-game-creater-action"]: item.function for item in AIActionRegistry(app).tools().tools}
    apply_body = tools["post.library.intelligence.assets.asset_id.apply"]["parameters"]["properties"]["body"]
    assert "report" in apply_body["properties"]
