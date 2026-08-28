from __future__ import annotations

from app.main import app
from app.services.ai_action_registry import AIActionRegistry


def test_full_asset_library_workflow_is_ai_discoverable() -> None:
    actions = {item.action_id: item for item in AIActionRegistry(app).catalog().actions}

    required = {
        "post.library.import.image",
        "post.library.import.images",
        "post.library.assets.asset_id.split",
        "get.library.assets.asset_id.hierarchy",
        "post.library.assets.asset_id.children",
        "delete.library.assets.asset_id.children.child_asset_id",
        "post.library.assets.asset_id.edit",
        "post.library.assets.bulk.edit",
        "post.library.assets.asset_id.versions.version.activate",
        "post.library.assets.parent_asset_id.reparent",
        "get.library.assets.asset_id.runtime.config",
        "patch.library.assets.asset_id.runtime.config",
        "post.library.assets.bulk.runtime.config",
        "get.library.assets.asset_id.collision.polygon",
        "patch.library.assets.asset_id.collision.polygon",
        "post.library.assets.asset_id.collision.polygon.generate",
        "get.library.animations",
        "post.library.animations",
        "get.library.animations.clip_id",
        "patch.library.animations.clip_id",
        "get.library.tilesets",
        "post.library.tilesets",
        "get.library.tilesets.tileset_id",
        "patch.library.tilesets.tileset_id",
        "post.library.packs.preflight",
        "post.library.packs.export",
        "post.library.packs.export.runtime",
        "post.library.packs.export.game.ready",
        "get.library.packs.pack_id.download",
    }
    assert required.issubset(actions)

    assert actions["post.library.assets.asset_id.edit"].risk.value == "write"
    assert actions["delete.library.assets.asset_id.children.child_asset_id"].requires_confirmation is True


def test_asset_workflow_tool_schemas_include_game_ready_2d_bodies() -> None:
    tools = {
        item.function["x-game-creater-action"]: item.function
        for item in AIActionRegistry(app).tools().tools
    }

    split_body = tools["post.library.assets.asset_id.split"]["parameters"]["properties"]["body"]
    edit_body = tools["post.library.assets.asset_id.edit"]["parameters"]["properties"]["body"]
    bulk_edit_body = tools["post.library.assets.bulk.edit"]["parameters"]["properties"]["body"]
    runtime_body = tools["patch.library.assets.asset_id.runtime.config"]["parameters"]["properties"]["body"]
    polygon_body = tools["post.library.assets.asset_id.collision.polygon.generate"]["parameters"]["properties"]["body"]
    animation_body = tools["post.library.animations"]["parameters"]["properties"]["body"]
    tileset_body = tools["post.library.tilesets"]["parameters"]["properties"]["body"]
    game_ready_body = tools["post.library.packs.export.game.ready"]["parameters"]["properties"]["body"]
    preflight_body = tools["post.library.packs.preflight"]["parameters"]["properties"]["body"]

    assert "mode" in split_body["properties"]
    assert "operation" in edit_body["properties"]
    assert "asset_ids" in bulk_edit_body["properties"]
    assert "edit" in bulk_edit_body["properties"]
    assert "pivot_x" in runtime_body["properties"]
    assert "collision_mode" in runtime_body["properties"]
    assert "max_points" in polygon_body["properties"]
    assert "frame_asset_ids" in animation_body["properties"]
    assert "fps" in animation_body["properties"]
    assert "tile_asset_ids" in tileset_body["properties"]
    assert "tile_width" in tileset_body["properties"]
    assert "animation_ids" in game_ready_body["properties"]
    assert "tileset_ids" in game_ready_body["properties"]
    assert "asset_ids" in preflight_body["properties"]
