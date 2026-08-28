from __future__ import annotations

import zipfile
from pathlib import Path

from PIL import Image

from app.main import app
from app.scene_composer_models import (
    ComposerExportTarget,
    ComposerItemCreate,
    ComposerItemPatch,
    ComposerLayerCreate,
    ComposerSceneCreate,
    ComposerTransform,
)
from app.services.ai_action_registry import AIActionRegistry
from app.services.asset_library_workflow import AssetLibraryWorkflowService
from app.services.pipeline import AssetSplitPipeline
from app.services.scene_composer import SceneComposerService


def _asset(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GAME_CREATER_MODE", "mock")
    workspace = tmp_path / "workspace"
    pipeline = AssetSplitPipeline(workspace)
    workflow = AssetLibraryWorkflowService(workspace, pipeline)
    image = tmp_path / "tree.png"
    Image.new("RGBA", (48, 72), (30, 150, 70, 255)).save(image)
    return workspace, workflow.import_image(image, name="Tree", category="vegetation")


def test_scene_composer_persists_layers_items_and_exports(tmp_path: Path, monkeypatch) -> None:
    workspace, asset = _asset(tmp_path, monkeypatch)
    service = SceneComposerService(workspace)
    scene = service.create_scene(ComposerSceneCreate(name="Forest", width=800, height=600, grid_size=32))
    assert scene.layers[0].name == "Default"
    assert service.db_path.parent == workspace.parent / ".game_creater_state"
    assert not str(service.db_path).startswith(str(workspace) + "/")

    scene = service.add_layer(scene.id, ComposerLayerCreate(name="Foreground", y_sort=True))
    foreground = next(layer for layer in scene.layers if layer.name == "Foreground")
    scene = service.add_item(
        scene.id,
        ComposerItemCreate(
            asset_id=asset.id,
            layer_id=foreground.id,
            transform=ComposerTransform(x=320, y=410, rotation_deg=5, scale_x=1.25, scale_y=1.25),
            z_index=7,
        ),
    )
    item = scene.items[0]
    assert item.asset_id == asset.id
    assert item.image_url.startswith("/workspace/")
    assert item.transform.x == 320

    scene = service.patch_item(
        scene.id,
        item.id,
        ComposerItemPatch(transform=ComposerTransform(x=360, y=420, rotation_deg=0, scale_x=1, scale_y=1)),
    )
    assert scene.items[0].transform.x == 360

    generic = service.export(scene.id, ComposerExportTarget.GENERIC)
    godot = service.export(scene.id, ComposerExportTarget.GODOT4)
    unity = service.export(scene.id, ComposerExportTarget.UNITY2D)
    with zipfile.ZipFile(generic.archive_path) as archive:
        assert "scene_composer.json" in archive.namelist()
        assert f"assets/{asset.id}.png" in archive.namelist()
    with zipfile.ZipFile(godot.archive_path) as archive:
        scene_text = archive.read("scene.tscn").decode("utf-8")
        assert "Sprite2D" in scene_text
        assert "position = Vector2(360.0000, 420.0000)" in scene_text
        assert "project.godot" in archive.namelist()
    with zipfile.ZipFile(unity.archive_path) as archive:
        names = set(archive.namelist())
        assert "Assets/GameCreaterComposer/Editor/GameCreaterComposerBuilder.cs" in names
        assert "Assets/GameCreaterComposer/scene_composer.json" in names


def test_scene_composer_actions_are_ai_native() -> None:
    actions = {item.action_id for item in AIActionRegistry(app).catalog().actions}
    required = {
        "get.library.composer.scenes",
        "post.library.composer.scenes",
        "post.library.composer.scenes.scene_id.layers",
        "post.library.composer.scenes.scene_id.items",
        "patch.library.composer.scenes.scene_id.items.item_id",
        "delete.library.composer.scenes.scene_id.items.item_id",
        "post.library.composer.scenes.scene_id.export.target",
    }
    assert required.issubset(actions)

    tools = {
        item.function["x-game-creater-action"]: item.function
        for item in AIActionRegistry(app).tools().tools
    }
    body = tools["post.library.composer.scenes.scene_id.items"]["parameters"]["properties"]["body"]
    assert "asset_id" in body["properties"]
    assert "transform" in body["properties"]
