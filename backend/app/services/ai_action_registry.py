from __future__ import annotations

import copy
import re
from typing import Any

from fastapi import FastAPI

from app.ai_control_models import (
    AIActionCatalog,
    AIActionDescriptor,
    AIRiskLevel,
    AIToolCatalog,
    AIToolDefinition,
)


HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


class AIActionRegistry:
    """Expose every product API operation as a machine-readable AI action.

    The registry is generated from the application's OpenAPI contract so UI,
    automation and AI agents share one source of truth instead of maintaining
    a second hand-written command surface.
    """

    def __init__(self, app: FastAPI) -> None:
        self.app = app

    def catalog(self) -> AIActionCatalog:
        schema = self.app.openapi()
        actions: list[AIActionDescriptor] = []
        for path, path_item in sorted(schema.get("paths", {}).items()):
            if not path.startswith("/api/v1/") or path.startswith("/api/v1/ai/"):
                continue
            for method, operation in path_item.items():
                if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                    continue
                actions.append(self._descriptor(method.upper(), path, operation))
        actions.sort(key=lambda item: item.action_id)
        return AIActionCatalog(actions=actions, total=len(actions))

    def tools(self) -> AIToolCatalog:
        openapi = self.app.openapi()
        components = (openapi.get("components") or {}).get("schemas") or {}
        tools = [self._to_tool(action, components) for action in self.catalog().actions]
        return AIToolCatalog(tools=tools, total=len(tools))

    def get(self, action_id: str) -> AIActionDescriptor:
        for action in self.catalog().actions:
            if action.action_id == action_id:
                return action
        raise KeyError(action_id)

    def _descriptor(self, method: str, path: str, operation: dict[str, Any]) -> AIActionDescriptor:
        risk, confirmation = self._risk(method, path)
        return AIActionDescriptor(
            action_id=self._action_id(method, path),
            method=method,
            path=path,
            summary=operation.get("summary") or operation.get("operationId") or f"{method} {path}",
            description=operation.get("description") or "",
            tags=list(operation.get("tags") or []),
            risk=risk,
            requires_confirmation=confirmation,
            parameters=list(operation.get("parameters") or []),
            request_body=operation.get("requestBody"),
            responses=dict(operation.get("responses") or {}),
        )

    @staticmethod
    def _action_id(method: str, path: str) -> str:
        clean = path.removeprefix("/api/v1/")
        clean = re.sub(r"[{}]", "", clean)
        clean = re.sub(r"[^a-zA-Z0-9]+", ".", clean).strip(".").lower()
        return f"{method.lower()}.{clean}"

    @staticmethod
    def _risk(method: str, path: str) -> tuple[AIRiskLevel, bool]:
        lower = path.lower()
        if "/checkout" in lower or "/seller/listings" in lower:
            return AIRiskLevel.COMMERCE, True
        if method == "DELETE":
            return AIRiskLevel.DESTRUCTIVE, True
        if any(token in lower for token in ("/projects/run", "/complete", "/refine-edge", "/point-segment")):
            return AIRiskLevel.EXPENSIVE, True
        if method in {"POST", "PUT", "PATCH"}:
            return AIRiskLevel.WRITE, False
        return AIRiskLevel.READ, False

    def _to_tool(self, action: AIActionDescriptor, components: dict[str, Any]) -> AIToolDefinition:
        properties: dict[str, Any] = {}
        required: list[str] = []

        for parameter in action.parameters:
            name = parameter.get("name")
            if not name:
                continue
            parameter_schema = self._resolve_schema(parameter.get("schema") or {"type": "string"}, components)
            parameter_schema["description"] = parameter.get("description") or f"{parameter.get('in', 'request')} parameter"
            properties[name] = parameter_schema
            if parameter.get("required"):
                required.append(name)

        body_schema: dict[str, Any] | None = None
        if action.request_body:
            content = action.request_body.get("content") or {}
            for content_type in ("application/json", "multipart/form-data", "application/x-www-form-urlencoded"):
                if content_type in content:
                    body_schema = self._resolve_schema(
                        content[content_type].get("schema") or {"type": "object"},
                        components,
                    )
                    break
        if body_schema is not None:
            properties["body"] = body_schema
            if action.request_body.get("required"):
                required.append("body")

        description = action.summary
        if action.description:
            description += f". {action.description}"
        description += f" [HTTP {action.method} {action.path}; risk={action.risk.value}]"
        if action.requires_confirmation:
            description += " Explicit user confirmation is required before execution."

        return AIToolDefinition(
            function={
                "name": action.action_id.replace(".", "__"),
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                },
                "x-game-creater-action": action.action_id,
                "x-http-method": action.method,
                "x-http-path": action.path,
                "x-risk": action.risk.value,
                "x-requires-confirmation": action.requires_confirmation,
            }
        )

    def _resolve_schema(
        self,
        value: Any,
        components: dict[str, Any],
        seen: tuple[str, ...] = (),
    ) -> Any:
        if isinstance(value, list):
            return [self._resolve_schema(item, components, seen) for item in value]
        if not isinstance(value, dict):
            return value

        ref = value.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            name = ref.rsplit("/", 1)[-1]
            if name in seen:
                return {
                    "type": "object",
                    "description": f"Recursive reference to {name}",
                }
            target = components.get(name)
            if isinstance(target, dict):
                merged = copy.deepcopy(target)
                for key, item in value.items():
                    if key != "$ref":
                        merged[key] = copy.deepcopy(item)
                return self._resolve_schema(merged, components, seen + (name,))

        return {
            key: self._resolve_schema(item, components, seen)
            for key, item in copy.deepcopy(value).items()
        }
