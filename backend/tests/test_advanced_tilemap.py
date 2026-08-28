from __future__ import annotations

import zipfile
from pathlib import Path

from PIL import Image

from app.advanced_tilemap_models import (
    TileCoordinate,
    TileMapCreateRequest,
    TileMapExportRequest,
    TileMapLayerCreate,
    TileMapLayerType,
    TileMapPaintRequest,
)
from app.asset_2d_models import AutoTileMode, TileSetCreateRequest, TileTerrainRule
from app.services.advanced_tilemap import AdvancedTileMapService
from app.services.asset_2d_resources import Asset2DResourceService
from app.services.asset_library_workflow import AssetLibraryWorkflowService
from app.services.pipeline import AssetSplitPipeline


def _setup(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GAME_CREATER_MODE", "mock")
    workspace = tmp_path / "workspace"
    pipeline = AssetSplitPipeline(workspace)
    workflow = AssetLibraryWorkflowService(workspace, pipeline)
    resources = Asset2DResourceService(workspace)
    tilemaps = AdvancedTileMapService(workspace)
    return workspace, workflow, resources, tilemaps


def _asset(workflow: AssetLibraryWorkflowService, tmp_path: Path, name: str):
    path = tmp_path / f"{name}.png"
    Image.new("RGBA", (32, 32), (255, 255, 255, 255)).save(path)
    return workflow.import_image(path, name=name, category="terrain")


def test_terrain_painter_recomputes_cardinal_autotile(tmp_path: Path, monkeypatch) -> None:
    _, workflow, resources, tilemaps = _setup(tmp_path, monkeypatch)
    south_connected = _asset(workflow, tmp_path, "south_connected")
    full = _asset(workflow, tmp_path, "full")
    tileset = resources.create_tileset(
        TileSetCreateRequest(
            name="grass",
            tile_asset_ids=[south_connected.id, full.id],
            tile_width=32,
            tile_height=32,
            terrain_tags=["grass"],
            autotile_mode=AutoTileMode.CARDINAL4,
            terrain_rules=[
                TileTerrainRule(asset_id=south_connected.id, terrain="grass", neighbor_mask=16, priority=0),
                TileTerrainRule(asset_id=full.id, terrain="grass", neighbor_mask=85, priority=10),
            ],
        )
    )
    project = tilemaps.create(TileMapCreateRequest(name="level", tileset_id=tileset.id, width=8, height=8))
    ground = project.layers[0]

    cells = [
        TileCoordinate(x=3, y=3),
        TileCoordinate(x=3, y=2),
        TileCoordinate(x=4, y=3),
        TileCoordinate(x=3, y=4),
        TileCoordinate(x=2, y=3),
    ]
    project = tilemaps.paint(project.id, TileMapPaintRequest(layer_id=ground.id, cells=cells, terrain="grass"))
    by_xy = {(cell.x, cell.y): cell for cell in project.layers[0].cells}
    assert by_xy[(3, 3)].asset_id == full.id
    assert by_xy[(3, 2)].asset_id == south_connected.id


def test_collision_navigation_layers_and_engine_exports(tmp_path: Path, monkeypatch) -> None:
    _, workflow, resources, tilemaps = _setup(tmp_path, monkeypatch)
    tile = _asset(workflow, tmp_path, "tile")
    tileset = resources.create_tileset(TileSetCreateRequest(name="ground", tile_asset_ids=[tile.id]))
    project = tilemaps.create(TileMapCreateRequest(name="demo", tileset_id=tileset.id, width=16, height=16))
    project = tilemaps.add_layer(project.id, TileMapLayerCreate(name="Collision", layer_type=TileMapLayerType.COLLISION))
    project = tilemaps.add_layer(project.id, TileMapLayerCreate(name="Navigation", layer_type=TileMapLayerType.NAVIGATION))
    collision = next(layer for layer in project.layers if layer.layer_type == TileMapLayerType.COLLISION)
    navigation = next(layer for layer in project.layers if layer.layer_type == TileMapLayerType.NAVIGATION)
    project = tilemaps.paint(project.id, TileMapPaintRequest(layer_id=collision.id, cells=[TileCoordinate(x=1, y=1)], asset_id=tile.id))
    project = tilemaps.paint(project.id, TileMapPaintRequest(layer_id=navigation.id, cells=[TileCoordinate(x=2, y=2)], asset_id=tile.id))
    assert any(layer.layer_type == TileMapLayerType.COLLISION and layer.cells for layer in project.layers)
    assert any(layer.layer_type == TileMapLayerType.NAVIGATION and layer.cells for layer in project.layers)

    godot = tilemaps.export(project.id, TileMapExportRequest(engine="godot4"))
    with zipfile.ZipFile(godot.archive_path) as archive:
        names = set(archive.namelist())
        assert "godot4/build_tilemap.gd" in names
        script = archive.read("godot4/build_tilemap.gd").decode("utf-8")
        assert "TileMapLayer.new()" in script
        assert "ResourceSaver.save" in script

    unity = tilemaps.export(project.id, TileMapExportRequest(engine="unity2d"))
    with zipfile.ZipFile(unity.archive_path) as archive:
        path = "unity2d/Assets/GameCreaterTileMap/Editor/GameCreaterTileMapBuilder.cs"
        assert path in archive.namelist()
        script = archive.read(path).decode("utf-8")
        assert "UnityEngine.Tilemaps" in script
        assert "Tilemap" in script
