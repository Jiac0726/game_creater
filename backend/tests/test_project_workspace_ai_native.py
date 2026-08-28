from __future__ import annotations

from app.main import app
from app.services.ai_action_registry import AIActionRegistry


def test_project_workspace_actions_are_ai_discoverable() -> None:
    actions = {item.action_id: item for item in AIActionRegistry(app).catalog().actions}
    required = {
        "get.library.project.workspaces",
        "post.library.project.workspaces",
        "get.library.project.workspaces.workspace_id",
        "patch.library.project.workspaces.workspace_id",
        "post.library.project.workspaces.workspace_id.assets",
        "patch.library.project.workspaces.workspace_id.assets.asset_id",
        "delete.library.project.workspaces.workspace_id.assets.asset_id",
        "post.library.project.workspaces.workspace_id.dependencies",
        "delete.library.project.workspaces.workspace_id.dependencies.source_asset_id.target_asset_id",
        "get.library.project.workspaces.workspace_id.resolve",
        "post.library.project.workspaces.workspace_id.export",
    }
    assert required.issubset(actions)
    assert actions["delete.library.project.workspaces.workspace_id.assets.asset_id"].requires_confirmation is True


def test_workspace_tool_schemas_expose_lock_and_dependency_fields() -> None:
    tools = {
        item.function["x-game-creater-action"]: item.function
        for item in AIActionRegistry(app).tools().tools
    }
    add = tools["post.library.project.workspaces.workspace_id.assets"]["parameters"]["properties"]["body"]
    patch = tools["patch.library.project.workspaces.workspace_id.assets.asset_id"]["parameters"]["properties"]["body"]
    dep = tools["post.library.project.workspaces.workspace_id.dependencies"]["parameters"]["properties"]["body"]
    assert {"asset_ids", "lock_to_current", "role"}.issubset(add["properties"])
    assert {"locked_version", "follow_active"}.issubset(patch["properties"])
    assert {"source_asset_id", "target_asset_id", "reason"}.issubset(dep["properties"])
