from __future__ import annotations

from app.main import app
from app.services.ai_action_registry import AIActionRegistry


def test_engine_sync_actions_are_ai_discoverable() -> None:
    actions = {item.action_id: item for item in AIActionRegistry(app).catalog().actions}
    required = {
        "get.library.engine.sync.profiles",
        "post.library.engine.sync.profiles",
        "get.library.engine.sync.profiles.profile_id",
        "patch.library.engine.sync.profiles.profile_id",
        "get.library.engine.sync.profiles.profile_id.plan",
        "post.library.engine.sync.profiles.profile_id.sync",
        "delete.library.engine.sync.profiles.profile_id.stale",
    }
    assert required.issubset(actions)
    assert actions["delete.library.engine.sync.profiles.profile_id.stale"].requires_confirmation is True


def test_engine_sync_tool_schemas_include_project_assets_and_prune_paths() -> None:
    tools = {
        item.function["x-game-creater-action"]: item.function
        for item in AIActionRegistry(app).tools().tools
    }
    create = tools["post.library.engine.sync.profiles"]["parameters"]["properties"]["body"]
    prune = tools["delete.library.engine.sync.profiles.profile_id.stale"]["parameters"]["properties"]["body"]
    assert {"name", "engine", "project_root", "asset_ids"}.issubset(create["properties"])
    assert "relative_paths" in prune["properties"]
