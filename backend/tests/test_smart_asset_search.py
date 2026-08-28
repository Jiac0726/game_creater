from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from app.main import app
from app.services.ai_action_registry import AIActionRegistry
from app.services.asset_library_workflow import AssetLibraryWorkflowService
from app.services.pipeline import AssetSplitPipeline
from app.services.smart_asset_search import SmartAssetSearchService
from app.smart_asset_search_models import SimilarAssetRequest, SmartAssetSearchRequest


def _setup(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GAME_CREATER_MODE", "mock")
    workspace = tmp_path / "workspace"
    pipeline = AssetSplitPipeline(workspace)
    workflow = AssetLibraryWorkflowService(workspace, pipeline)
    return workspace, workflow


def _make(path: Path, *, variant: int = 0):
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((8 + variant, 8, 54, 54), fill=(120, 90, 40, 255))
    draw.rectangle((20, 20, 42, 42), fill=(70, 50, 20, 255))
    image.save(path)


def test_text_search_uses_metadata_and_ontology_expansion(tmp_path: Path, monkeypatch) -> None:
    workspace, workflow = _setup(tmp_path, monkeypatch)
    tree_path = tmp_path / "tree.png"
    barrel_path = tmp_path / "barrel.png"
    _make(tree_path)
    _make(barrel_path, variant=2)
    tree = workflow.import_image(tree_path, name="Ancient Tree", category="vegetation", tags=["forest", "tree"])
    barrel = workflow.import_image(barrel_path, name="Old Wooden Barrel", category="props", tags=["wood", "tavern"])

    service = SmartAssetSearchService(workspace)
    result = service.search(SmartAssetSearchRequest(query="森林里的树", limit=10))
    assert result.providers == ["ontology_lexical"]
    assert result.hits
    assert result.hits[0].asset.id == tree.id
    assert result.hits[0].score > 0
    assert barrel.id in {item.asset.id for item in service.search(SmartAssetSearchRequest(query="wood barrel")).hits}


def test_similar_search_uses_active_image_dhash(tmp_path: Path, monkeypatch) -> None:
    workspace, workflow = _setup(tmp_path, monkeypatch)
    a_path = tmp_path / "a.png"
    b_path = tmp_path / "b.png"
    c_path = tmp_path / "c.png"
    _make(a_path)
    _make(b_path, variant=1)
    Image.new("RGBA", (64, 64), (255, 255, 255, 255)).save(c_path)
    a = workflow.import_image(a_path, name="Crate A", category="props", tags=["wood"])
    b = workflow.import_image(b_path, name="Crate B", category="props", tags=["wood"])
    workflow.import_image(c_path, name="White", category="effects")

    result = SmartAssetSearchService(workspace).similar(SimilarAssetRequest(asset_id=a.id, limit=5))
    assert result.hits[0].asset.id == b.id
    assert result.hits[0].score >= result.hits[-1].score


def test_smart_search_actions_are_ai_discoverable() -> None:
    actions = {item.action_id for item in AIActionRegistry(app).catalog().actions}
    assert "get.library.smart.search.providers" in actions
    assert "post.library.smart.search.text" in actions
    assert "post.library.smart.search.similar" in actions
    tools = {item.function["x-game-creater-action"]: item.function for item in AIActionRegistry(app).tools().tools}
    body = tools["post.library.smart.search.text"]["parameters"]["properties"]["body"]
    assert "query" in body["properties"]
