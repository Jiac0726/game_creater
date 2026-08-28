from __future__ import annotations

from app.main import app
from app.services.ai_action_registry import AIActionRegistry


def test_full_asset_library_workflow_is_ai_discoverable() -> None:
    actions = {item.action_id: item for item in AIActionRegistry(app).catalog().actions}

    required = {
        "post.library.import.image",
        "post.library.assets.asset_id.split",
        "get.library.assets.asset_id.hierarchy",
        "post.library.assets.asset_id.children",
        "delete.library.assets.asset_id.children.child_asset_id",
        "post.library.assets.asset_id.edit",
        "post.library.packs.export",
        "get.library.packs.pack_id.download",
    }
    assert required.issubset(actions)

    assert actions["post.library.assets.asset_id.edit"].risk.value == "write"
    assert actions["delete.library.assets.asset_id.children.child_asset_id"].requires_confirmation is True


def test_asset_workflow_tool_schemas_include_split_and_edit_bodies() -> None:
    tools = {
        item.function["x-game-creater-action"]: item.function
        for item in AIActionRegistry(app).tools().tools
    }

    split_body = tools["post.library.assets.asset_id.split"]["parameters"]["properties"]["body"]
    edit_body = tools["post.library.assets.asset_id.edit"]["parameters"]["properties"]["body"]
    export_body = tools["post.library.packs.export"]["parameters"]["properties"]["body"]

    assert "mode" in split_body["properties"]
    assert "operation" in edit_body["properties"]
    assert "engine" in export_body["properties"]
