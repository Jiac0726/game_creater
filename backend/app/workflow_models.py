from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class WorkflowStage(str, Enum):
    CREATED = "CREATED"
    SEMANTIC_PLANNING = "SEMANTIC_PLANNING"
    PROMPT_READY = "PROMPT_READY"
    GENERATING = "GENERATING"
    IMAGE_READY = "IMAGE_READY"
    DETECTING = "DETECTING"
    SEGMENTING = "SEGMENTING"
    ASSET_REVIEW = "ASSET_REVIEW"
    COMPLETING = "COMPLETING"
    ENGINE_EXPORT = "ENGINE_EXPORT"
    DONE = "DONE"
    FAILED = "FAILED"


class WorkflowEvent(BaseModel):
    stage: WorkflowStage
    status: str = "ok"
    message: str = ""
    created_at: str
    data: dict[str, Any] = Field(default_factory=dict)


class PlannedAsset(BaseModel):
    zh: str
    en: str
    group: str
    score: float = 0.0
    source: str = "semantic"


class AssetPlan(BaseModel):
    concept: str
    matched_concept: str | None = None
    modifiers: list[str] = Field(default_factory=list)
    assets: list[PlannedAsset] = Field(default_factory=list)
    detection_prompts: list[str] = Field(default_factory=list)


class GenerationSpec(BaseModel):
    provider: str = "mock"
    model: str | None = None
    size: str = "1536x1024"
    quality: str = "medium"
    prompt: str = ""
    negative_prompt: str = ""


class GenerationResult(BaseModel):
    provider: str
    model: str
    image_file: str
    prompt: str
    size: str
    quality: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompletionJob(BaseModel):
    id: str
    asset_id: str
    mode: str = "occlusion_completion"
    status: str = "pending"
    provider: str = "local"
    source_asset: str | None = None
    output_asset: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectRecord(BaseModel):
    project_id: str
    concept: str
    stage: WorkflowStage = WorkflowStage.CREATED
    created_at: str
    updated_at: str
    asset_plan: AssetPlan | None = None
    generation: GenerationResult | None = None
    scene_id: str | None = None
    completion_jobs: list[CompletionJob] = Field(default_factory=list)
    exports: dict[str, str] = Field(default_factory=dict)
    events: list[WorkflowEvent] = Field(default_factory=list)
    error: str | None = None


class RunProjectRequest(BaseModel):
    concept: str
    semantic_depth: int = 2
    max_per_group: int = 12
    provider: str = "mock"
    model: str | None = None
    size: str = "1536x1024"
    quality: str = "medium"
    auto_split: bool = True


class RunProjectResponse(BaseModel):
    project: ProjectRecord
