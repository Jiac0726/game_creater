from __future__ import annotations

import json

from app.main import app
from app.services.ai_action_registry import AIActionRegistry


HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def test_every_v1_product_operation_is_exposed_as_ai_action() -> None:
    registry = AIActionRegistry(app)
    catalog = registry.catalog()
    openapi = app.openapi()

    expected = 0
    for path, path_item in openapi["paths"].items():
        if not path.startswith("/api/v1/") or path.startswith("/api/v1/ai/"):
            continue
        expected += sum(1 for method in path_item if method.lower() in HTTP_METHODS)

    assert catalog.total == expected
    assert catalog.total > 20
    assert len({action.action_id for action in catalog.actions}) == catalog.total
    assert all(not action.path.startswith("/api/v1/ai/") for action in catalog.actions)


def test_critical_product_capabilities_have_stable_ai_actions() -> None:
    actions = {item.action_id: item for item in AIActionRegistry(app).catalog().actions}

    assert "post.projects.run" in actions
    assert "post.scenes.analyze" in actions
    assert "patch.library.assets.asset_id" in actions
    assert "delete.scenes.scene_id.assets.asset_id" in actions
    assert "post.scenes.scene_id.assets.asset_id.complete" in actions
    assert "post.store.checkout" in actions
    assert "post.store.seller.listings" in actions
    assert "get.scenes.scene_id.export.godot.zip" in actions
    assert "get.scenes.scene_id.export.unity.zip" in actions


def test_ai_risk_policy_requires_confirmation_for_sensitive_actions() -> None:
    actions = {item.action_id: item for item in AIActionRegistry(app).catalog().actions}

    assert actions["delete.scenes.scene_id.assets.asset_id"].requires_confirmation is True
    assert actions["delete.scenes.scene_id.assets.asset_id"].risk.value == "destructive"
    assert actions["post.store.checkout"].requires_confirmation is True
    assert actions["post.store.checkout"].risk.value == "commerce"
    assert actions["post.projects.run"].requires_confirmation is True
    assert actions["post.projects.run"].risk.value == "expensive"
    assert actions["get.models.status"].requires_confirmation is False
    assert actions["get.models.status"].risk.value == "read"


def test_ai_tool_schemas_are_self_contained_and_include_complex_request_bodies() -> None:
    tools = AIActionRegistry(app).tools()
    by_action = {
        tool.function["x-game-creater-action"]: tool.function
        for tool in tools.tools
    }

    assert tools.total > 20
    assert "$ref" not in json.dumps([tool.model_dump() for tool in tools.tools], ensure_ascii=False)

    project_run = by_action["post.projects.run"]
    project_body = project_run["parameters"]["properties"]["body"]
    assert "concept" in project_body["properties"]
    assert "provider" in project_body["properties"]

    checkout = by_action["post.store.checkout"]
    checkout_body = checkout["parameters"]["properties"]["body"]
    assert "listing_ids" in checkout_body["properties"]
    assert checkout["x-requires-confirmation"] is True


def test_ai_endpoints_exist_in_openapi_but_do_not_recursively_become_tools() -> None:
    paths = app.openapi()["paths"]
    assert "/api/v1/ai/actions" in paths
    assert "/api/v1/ai/tools" in paths
    assert "/api/v1/ai/policy" in paths

    tool_paths = {item.path for item in AIActionRegistry(app).catalog().actions}
    assert not any(path.startswith("/api/v1/ai/") for path in tool_paths)
