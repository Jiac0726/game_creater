from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException

from app.ai_control_models import AIActionCatalog, AIActionDescriptor, AIToolCatalog
from app.services.ai_action_registry import AIActionRegistry


def build_ai_control_router(app: FastAPI) -> APIRouter:
    router = APIRouter(prefix="/api/v1/ai", tags=["ai-control"])
    registry = AIActionRegistry(app)

    @router.get("/actions", response_model=AIActionCatalog)
    def list_actions() -> AIActionCatalog:
        """Machine-readable catalog for every non-AI v1 product operation."""
        return registry.catalog()

    @router.get("/actions/{action_id}", response_model=AIActionDescriptor)
    def get_action(action_id: str) -> AIActionDescriptor:
        try:
            return registry.get(action_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="AI action not found") from exc

    @router.get("/tools", response_model=AIToolCatalog)
    def list_tools() -> AIToolCatalog:
        """Function-tool representation suitable for LLM/agent adapters."""
        return registry.tools()

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

    return router
