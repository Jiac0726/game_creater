from __future__ import annotations

import json
import zipfile
from pathlib import Path

from PIL import Image

from app.asset_runtime_models import (
    AssetRuntimeConfigPatch,
    CollisionMode,
    RuntimeAssetPackExportRequest,
)
from app.asset_workflow_models import AssetPackEngine
from app.services.asset_library_workflow import AssetLibraryWorkflowService
from app.services.asset_runtime_config import AssetRuntimeConfigService
from app.services.asset_runtime_pack import AssetRuntimePackService
from app.services.pipeline import AssetSplitPipeline


def _setup(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GAME_CREATER_MODE", "mock")
    workspace = tmp_path / "workspace"
    pipeline = AssetSplitPipeline(workspace)
    workflow = AssetLibraryWorkflowService(workspace, pipeline)
    runtime = AssetRuntimeConfigService(workspace)
    packer = AssetRuntimePackService(workspace, pipeline)
    image_path = tmp_path / "barrel.png"
    Image.new("RGBA", (64, 96), (180, 120, 60, 255)).save(image_path)
    asset = workflow.import_image(image_path, name="Barrel", category="prop")
    return workflow, runtime, packer, asset


def test_runtime_config_defaults_and_patch_are_persisted(tmp_path: Path, monkeypatch) -> None:
    _, runtime, _, asset = _setup(tmp_path, monkeypatch)
    default = runtime.get(asset.id)
    assert default.pivot_x == 0.5
    assert default.pivot_y == 1.0
    assert default.pixels_per_unit == 100.0
    assert default.collision_mode == CollisionMode.NONE

    updated = runtime.patch(
        asset.id,
        AssetRuntimeConfigPatch(
            pivot_x=0.45,
            pivot_y=0.9,
            pixels_per_unit=64,
            render_layer="foreground_props",
            sorting_order=120,
            collision_mode=CollisionMode.BOX,
            collision_is_trigger=True,
            gameplay_tags=["obstacle", "lootable", "obstacle"],
        ),
    )
    assert updated.pivot_x == 0.45
    assert updated.pixels_per_unit == 64
    assert updated.render_layer == "foreground_props"
    assert updated.sorting_order == 120
    assert updated.collision_mode == CollisionMode.BOX
    assert updated.collision_is_trigger is True
    assert updated.gameplay_tags == ["obstacle", "lootable"]
    assert runtime.get(asset.id) == updated


def test_runtime_godot_pack_contains_prefab_with_pivot_sorting_and_collision(tmp_path: Path, monkeypatch) -> None:
    _, runtime, packer, asset = _setup(tmp_path, monkeypatch)
    runtime.patch(
        asset.id,
        AssetRuntimeConfigPatch(
            pivot_x=0.5,
            pivot_y=1.0,
            sorting_order=7,
            collision_mode=CollisionMode.BOX,
        ),
    )

    result = packer.export(
        RuntimeAssetPackExportRequest(
            name="Godot Runtime Pack",
            asset_ids=[asset.id],
            engine=AssetPackEngine.GODOT4,
        )
    )
    assert result.runtime_config_count == 1
    with zipfile.ZipFile(result.archive_path) as bundle:
        names = set(bundle.namelist())
        assert "runtime_config.json" in names
        assert f"godot4/prefabs/{asset.id}.tscn" in names
        scene = bundle.read(f"godot4/prefabs/{asset.id}.tscn").decode("utf-8")
        assert 'type="Sprite2D"' in scene
        assert "z_index = 7" in scene
        assert 'type="StaticBody2D"' in scene
        assert 'type="RectangleShape2D"' in scene
        resource = bundle.read(f"godot4/resources/{asset.id}.tres").decode("utf-8")
        assert "res://godot4/assets/" in resource


def test_runtime_unity_pack_contains_prefab_builder_and_runtime_snapshot(tmp_path: Path, monkeypatch) -> None:
    _, runtime, packer, asset = _setup(tmp_path, monkeypatch)
    runtime.patch(
        asset.id,
        AssetRuntimeConfigPatch(
            pivot_x=0.25,
            pivot_y=0.8,
            pixels_per_unit=80,
            sorting_order=12,
            collision_mode=CollisionMode.BOX,
            gameplay_tags=["interactable"],
        ),
    )

    result = packer.export(
        RuntimeAssetPackExportRequest(
            name="Unity Runtime Pack",
            asset_ids=[asset.id],
            engine=AssetPackEngine.UNITY2D,
        )
    )
    with zipfile.ZipFile(result.archive_path) as bundle:
        names = set(bundle.namelist())
        assert "runtime_config.json" in names
        assert "unity2d/Assets/GameCreaterPack/runtime_config.json" in names
        assert "unity2d/Assets/GameCreaterPack/Runtime/GameCreaterRuntimeMetadata.cs" in names
        assert "unity2d/Assets/GameCreaterPack/Editor/GameCreaterRuntimePrefabBuilder.cs" in names
        script = bundle.read(
            "unity2d/Assets/GameCreaterPack/Editor/GameCreaterRuntimePrefabBuilder.cs"
        ).decode("utf-8")
        assert "spritePivot" in script
        assert "spritePixelsPerUnit" in script
        assert "sortingOrder" in script
        assert "BoxCollider2D" in script
        runtime_doc = json.loads(bundle.read("runtime_config.json").decode("utf-8"))
        assert runtime_doc["assets"][0]["asset_id"] == asset.id
        assert runtime_doc["assets"][0]["gameplay_tags"] == ["interactable"]
