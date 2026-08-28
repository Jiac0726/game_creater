from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.ai_control_models import AIActionCatalog, AIActionDescriptor, AIToolCatalog
from app.services.ai_action_registry import AIActionRegistry


router = APIRouter(prefix="/ai", tags=["ai-control"])


def _registry(request: Request) -> AIActionRegistry:
    return AIActionRegistry(request.app)


@router.get("/actions", response_model=AIActionCatalog)
def list_actions(request: Request) -> AIActionCatalog:
    """Machine-readable catalog for every non-AI v1 product operation."""
    return _registry(request).catalog()


@router.get("/actions/{action_id}", response_model=AIActionDescriptor)
def get_action(action_id: str, request: Request) -> AIActionDescriptor:
    try:
        return _registry(request).get(action_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="AI action not found") from exc


@router.get("/tools", response_model=AIToolCatalog)
def list_tools(request: Request) -> AIToolCatalog:
    """Function-tool representation suitable for LLM/agent adapters."""
    return _registry(request).tools()


@router.get("/policy")
def ai_policy() -> dict:
    return {
        "contract": "Every user-visible product operation must have a backend API operation and therefore an AI action.",
        "ui_rule": "UI controls call the same backend capabilities exposed to AI; UI-only business mutations are prohibited.",
        "confirmation": {
            "commerce": True,
            "destructive": True,
            "expensive": True,
            "ordinary_write": False,
            "read": False,
        },
        "execution_model": "Agents invoke the target HTTP method/path declared by each action. The AI manifest is discovery/policy metadata, not a shadow implementation.",
    }
