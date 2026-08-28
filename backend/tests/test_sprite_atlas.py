from __future__ import annotations

import json
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

from app.main import app
from app.services.ai_action_registry import AIActionRegistry
from app.services.asset_library_workflow import AssetLibraryWorkflowService
from app.services.pipeline import AssetSplitPipeline
from app.services.sprite_atlas import SpriteAtlasService
from app.sprite_atlas_models import AtlasBuildRequest, AtlasEngine


def _setup(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GAME_CREATER_MODE", "mock")
    workspace = tmp_path / "workspace"
    pipeline = AssetSplitPipeline(workspace)
    return workspace, AssetLibraryWorkflowService(workspace, pipeline)


def _sprite(path: Path, width: int, height: int, inset: int):
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((inset, inset, width - inset - 1, height - inset - 1), fill=(200, 120, 40, 255))
    image.save(path)


def test_atlas_trim_padding_and_power_of_two(tmp_path: Path, monkeypatch) -> None:
    workspace, workflow = _setup(tmp_path, monkeypatch)
    a_path = tmp_path / "a.png"
    b_path = tmp_path / "b.png"
    _sprite(a_path, 50, 42, 5)
    _sprite(b_path, 38, 60, 4)
    a = workflow.import_image(a_path, name="A", category="props")
    b = workflow.import_image(b_path, name="B", category="props")
    result = SpriteAtlasService(workspace).build(
        AtlasBuildRequest(name="props", asset_ids=[a.id, b.id], max_width=128, max_height=128, padding=2, power_of_two=True)
    )
    assert result.sprite_count == 2
    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    assert len(manifest["sprites"]) == 2
    assert any(item["trim_x"] > 0 for item in manifest["sprites"])
    for page in manifest["pages"]:
        assert page["width"] & (page["width"] - 1) == 0
        assert page["height"] & (page["height"] - 1) == 0
    with zipfile.ZipFile(result.archive_path) as archive:
        assert "atlas.json" in archive.namelist()
        assert any(name.startswith("atlas_") and name.endswith(".png") for name in archive.namelist())


def test_atlas_engine_delivery(tmp_path: Path, monkeypatch) -> None:
    workspace, workflow = _setup(tmp_path, monkeypatch)
    path = tmp_path / "sprite.png"
    _sprite(path, 48, 48, 3)
    asset = workflow.import_image(path, name="Sprite", category="props")
    service = SpriteAtlasService(workspace)
    godot = service.build(AtlasBuildRequest(name="godot", asset_ids=[asset.id], engine=AtlasEngine.GODOT4, max_width=128, max_height=128))
    unity = service.build(AtlasBuildRequest(name="unity", asset_ids=[asset.id], engine=AtlasEngine.UNITY2D, max_width=128, max_height=128))
    with zipfile.ZipFile(godot.archive_path) as archive:
        assert f"godot4/resources/{asset.id}.tres" in archive.namelist()
        text = archive.read(f"godot4/resources/{asset.id}.tres").decode("utf-8")
        assert "AtlasTexture" in text and "region = Rect2" in text
    with zipfile.ZipFile(unity.archive_path) as archive:
        builder = archive.read("unity2d/Assets/GameCreaterAtlas/Editor/GameCreaterAtlasImporter.cs").decode("utf-8")
        assert "SpriteImportMode.Multiple" in builder
        assert "SpriteMetaData" in builder


def test_atlas_actions_are_ai_native() -> None:
    actions = {item.action_id for item in AIActionRegistry(app).catalog().actions}
    assert "post.library.atlases" in actions
    assert "get.library.atlases.atlas_id.download" in actions
    tools = {item.function["x-game-creater-action"]: item.function for item in AIActionRegistry(app).tools().tools}
    body = tools["post.library.atlases"]["parameters"]["properties"]["body"]
    assert "asset_ids" in body["properties"]
    assert "padding" in body["properties"]
    assert "power_of_two" in body["properties"]
