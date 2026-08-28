from __future__ import annotations

from app.main import app
from app.services.ai_action_registry import AIActionRegistry


def test_advanced_tilemap_actions_are_ai_discoverable() -> None:
    actions = {item.action_id: item for item in AIActionRegistry(app).catalog().actions}
    required = {
        "get.library.tilemaps",
        "post.library.tilemaps",
        "get.library.tilemaps.map_id",
        "post.library.tilemaps.map_id.layers",
        "post.library.tilemaps.map_id.paint",
        "post.library.tilemaps.map_id.erase",
        "post.library.tilemaps.map_id.export",
    }
    assert required.issubset(actions)


def test_advanced_tilemap_tool_schemas_include_paint_and_export_bodies() -> None:
    tools = {
        item.function["x-game-creater-action"]: item.function
        for item in AIActionRegistry(app).tools().tools
    }
    paint = tools["post.library.tilemaps.map_id.paint"]["parameters"]["properties"]["body"]
    export = tools["post.library.tilemaps.map_id.export"]["parameters"]["properties"]["body"]
    layer = tools["post.library.tilemaps.map_id.layers"]["parameters"]["properties"]["body"]
    assert {"layer_id", "cells", "asset_id", "terrain"}.issubset(paint["properties"])
    assert "engine" in export["properties"]
    assert "layer_type" in layer["properties"]
