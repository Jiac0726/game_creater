from __future__ import annotations

from app.main import app
from app.services.ai_action_registry import AIActionRegistry


def test_asset_pack_actions_are_ai_discoverable() -> None:
    actions = {item.action_id: item for item in AIActionRegistry(app).catalog().actions}
    required = {
        "get.library.package.system.packs",
        "post.library.package.system.packs",
        "get.library.package.system.packs.pack_id",
        "patch.library.package.system.packs.pack_id",
        "get.library.package.system.packs.pack_id.releases",
        "post.library.package.system.packs.pack_id.releases",
        "post.library.package.system.packs.pack_id.install",
        "delete.library.package.system.packs.pack_id.install",
        "get.library.package.system.installed",
        "get.library.package.system.updates",
        "post.library.package.system.packs.pack_id.export",
    }
    assert required.issubset(actions)
    assert actions["delete.library.package.system.packs.pack_id.install"].requires_confirmation is True


def test_asset_pack_tool_schemas_include_version_and_dependencies() -> None:
    tools = {
        item.function["x-game-creater-action"]: item.function
        for item in AIActionRegistry(app).tools().tools
    }
    create = tools["post.library.package.system.packs"]["parameters"]["properties"]["body"]
    release = tools["post.library.package.system.packs.pack_id.releases"]["parameters"]["properties"]["body"]
    install = tools["post.library.package.system.packs.pack_id.install"]["parameters"]["properties"]["body"]
    assert {"name", "asset_ids", "dependencies"}.issubset(create["properties"])
    assert "version" in release["properties"]
    assert "version" in install["properties"]
