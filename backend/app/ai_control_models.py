from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AIRiskLevel(str, Enum):
    READ = "read"
    WRITE = "write"
    EXPENSIVE = "expensive"
    DESTRUCTIVE = "destructive"
    COMMERCE = "commerce"


class AIActionDescriptor(BaseModel):
    action_id: str
    method: str
    path: str
    summary: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    risk: AIRiskLevel = AIRiskLevel.READ
    requires_confirmation: bool = False
    parameters: list[dict[str, Any]] = Field(default_factory=list)
    request_body: dict[str, Any] | None = None
    responses: dict[str, Any] = Field(default_factory=dict)


class AIActionCatalog(BaseModel):
    actions: list[AIActionDescriptor]
    total: int
    generated_from: str = "fastapi-openapi"


class AIToolDefinition(BaseModel):
    type: str = "function"
    function: dict[str, Any]


class AIToolCatalog(BaseModel):
    tools: list[AIToolDefinition]
    total: int
    protocol: str = "game-creater-ai-tools-v1"
