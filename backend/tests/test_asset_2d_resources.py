from __future__ import annotations

import json
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

from app.asset_2d_models import (
    AnimationClipCreateRequest,
    CollisionPolygonGenerateRequest,
    GameReadyPackExportRequest,
    TileSetCreateRequest,
)
from app.asset_runtime_models import AssetRuntimeConfigPatch, CollisionMode
from app.asset_workflow_models import AssetPackEngine
from app.services.asset_2d_pack import Asset2DGameReadyPackService
from app.services.asset_2d_resources import Asset2DResourceService
from app.services.asset_library_workflow import AssetLibraryWorkflowService
from app.services.asset_runtime_config import AssetRuntimeConfigService
from app.services.pipeline import AssetSplitPipeline


def _setup(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GAME_CREATER_MODE", "mock")
    workspace = tmp_path / "workspace"
    pipeline = AssetSplitPipeline(workspace)
    workflow = AssetLibraryWorkflowService(workspace, pipeline)
    resources = Asset2DResourceService(workspace)
    runtime = AssetRuntimeConfigService(workspace)
    pack = Asset2DGameReadyPackService(workspace, pipeline)
    return workspace, workflow, resources, runtime, pack


def _asset(workflow: AssetLibraryWorkflowService, tmp_path: Path, name: str, shape: str = "rect"):
    path = tmp_path / f"{name}.png"
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if shape == "triangle":
        draw.polygon([(8, 54), (32, 6), (56, 54)], fill=(255, 255, 255, 255))
    else:
        draw.rectangle((10, 12, 53, 55), fill=(255, 255, 255, 255))
    image.save(path)
    return workflow.import_image(path, name=name, category="prop")


def test_polygon_generation_uses_mask_and_runtime_can_select_polygon(tmp_path: Path, monkeypatch) -> None:
    _, workflow, resources, runtime, _ = _setup(tmp_path, monkeypatch)
    asset = _asset(workflow, tmp_path, "triangle", "triangle")

    polygon = resources.generate_polygon(
        asset.id,
        CollisionPolygonGenerateRequest(alpha_threshold=1, max_points=12),
    )
    assert polygon.asset_id == asset.id
    assert polygon.source == "mask_convex_hull"
    assert 3 <= len(polygon.points) <= 12
    assert all(0 <= point.x <= 1 and 0 <= point.y <= 1 for point in polygon.points)

    config = runtime.patch(
        asset.id,
        AssetRuntimeConfigPatch(collision_mode=CollisionMode.POLYGON, collision_is_trigger=True),
    )
    assert config.collision_mode == CollisionMode.POLYGON
    assert config.collision_is_trigger is True


def test_animation_keeps_frame_order_and_tileset_keeps_unique_tiles(tmp_path: Path, monkeypatch) -> None:
    _, workflow, resources, _, _ = _setup(tmp_path, monkeypatch)
    a = _asset(workflow, tmp_path, "frame_a")
    b = _asset(workflow, tmp_path, "frame_b")

    clip = resources.create_animation(
        AnimationClipCreateRequest(
            name="idle",
            frame_asset_ids=[a.id, b.id, a.id],
            fps=6,
            loop=True,
        )
    )
    assert clip.frame_asset_ids == [a.id, b.id, a.id]
    assert clip.fps == 6

    tileset = resources.create_tileset(
        TileSetCreateRequest(
            name="forest_ground",
            tile_asset_ids=[a.id, b.id, a.id],
            tile_width=32,
            tile_height=32,
            terrain_tags=["grass", "grass", "ground"],
        )
    )
    assert tileset.tile_asset_ids == [a.id, b.id]
    assert tileset.terrain_tags == ["grass", "ground"]


def test_game_ready_godot_pack_contains_polygon_animation_and_tileset(tmp_path: Path, monkeypatch) -> None:
    _, workflow, resources, runtime, pack = _setup(tmp_path, monkeypatch)
    a = _asset(workflow, tmp_path, "hero_a", "triangle")
    b = _asset(workflow, tmp_path, "hero_b")
    resources.generate_polygon(a.id, CollisionPolygonGenerateRequest(max_points=10))
    runtime.patch(a.id, AssetRuntimeConfigPatch(collision_mode=CollisionMode.POLYGON))
    animation = resources.create_animation(
        AnimationClipCreateRequest(name="walk", frame_asset_ids=[a.id, b.id], fps=8, loop=True)
    )
    tileset = resources.create_tileset(
        TileSetCreateRequest(name="ground", tile_asset_ids=[b.id], tile_width=32, tile_height=32)
    )

    result = pack.export(
        GameReadyPackExportRequest(
            name="Godot Game Ready",
            asset_ids=[a.id],
            animation_ids=[animation.id],
            tileset_ids=[tileset.id],
            engine=AssetPackEngine.GODOT4,
        )
    )
    assert result.asset_count == 2  # b is added automatically as an animation/tile dependency.
    assert result.animation_count == 1
    assert result.tileset_count == 1
    assert result.polygon_collision_count == 1

    with zipfile.ZipFile(result.archive_path) as archive:
        names = set(archive.namelist())
        assert "game_ready_2d.json" in names
        assert f"godot4/animations/{animation.id}.tscn" in names
        assert f"godot4/tilesets/build_{tileset.id}.gd" in names
        prefab = archive.read(f"godot4/prefabs/{a.id}.tscn").decode("utf-8")
        assert "CollisionPolygon2D" in prefab
        polygon_line = next(line for line in prefab.splitlines() if line.startswith("polygon = PackedVector2Array"))
        assert "Vector2(" not in polygon_line
        assert polygon_line.count(",") >= 5
        animation_scene = archive.read(f"godot4/animations/{animation.id}.tscn").decode("utf-8")
        assert "AnimatedSprite2D" in animation_scene
        assert "SpriteFrames" in animation_scene
        assert '"loop": 1' in animation_scene
        doc = json.loads(archive.read("game_ready_2d.json"))
        assert doc["animations"][0]["frame_asset_ids"] == [a.id, b.id]


def test_game_ready_unity_pack_contains_native_builders(tmp_path: Path, monkeypatch) -> None:
    _, workflow, resources, runtime, pack = _setup(tmp_path, monkeypatch)
    a = _asset(workflow, tmp_path, "tile_a", "triangle")
    b = _asset(workflow, tmp_path, "tile_b")
    resources.generate_polygon(a.id, CollisionPolygonGenerateRequest(max_points=10))
    runtime.patch(a.id, AssetRuntimeConfigPatch(collision_mode=CollisionMode.POLYGON))
    animation = resources.create_animation(
        AnimationClipCreateRequest(name="blink", frame_asset_ids=[a.id, b.id], fps=4, loop=False)
    )
    tileset = resources.create_tileset(
        TileSetCreateRequest(name="tiles", tile_asset_ids=[a.id, b.id], tile_width=64, tile_height=64)
    )

    result = pack.export(
        GameReadyPackExportRequest(
            name="Unity Game Ready",
            asset_ids=[a.id],
            animation_ids=[animation.id],
            tileset_ids=[tileset.id],
            engine=AssetPackEngine.UNITY2D,
        )
    )
    with zipfile.ZipFile(result.archive_path) as archive:
        names = set(archive.namelist())
        builder_path = "unity2d/Assets/GameCreaterPack/Editor/GameCreaterGameReady2DBuilder.cs"
        assert builder_path in names
        assert "unity2d/Assets/GameCreaterPack/game_ready_2d.json" in names
        builder = archive.read(builder_path).decode("utf-8")
        assert "PolygonCollider2D" in builder
        assert "AnimationClip" in builder
        assert "UnityEngine.Tilemaps" in builder
        assert "AssetDatabase.CreateAsset" in builder
