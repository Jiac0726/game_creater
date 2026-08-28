from __future__ import annotations

from pydantic import BaseModel, Field

from app.models import BBox


class AssetCompletionRequest(BaseModel):
    rect: BBox
    provider: str = "mock"
    prompt: str | None = None
    negative_prompt: str = ""
    mode: str = "occlusion_completion"


class AssetCompletionResult(BaseModel):
    job_id: str
    scene_id: str
    asset_id: str
    provider: str
    mode: str
    rect: BBox
    source_asset: str
    completed_scene: str
    completed_asset: str
    completed_mask: str
    resegmented: bool = False
    confidence: float = 0.0
    metadata: dict = Field(default_factory=dict)
