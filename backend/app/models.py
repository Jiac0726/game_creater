from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class BBox(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int


class AssetRecord(BaseModel):
    id: str
    label: str
    category: str = "uncategorized"
    confidence: float = 0.0
    bbox: BBox
    image: str
    mask: str
    source_position: dict = Field(default_factory=dict)
    completed: bool = False
    notes: Optional[str] = None


class SceneManifest(BaseModel):
    scene_id: str
    source_image: str
    width: int
    height: int
    mode: str
    prompts: List[str]
    assets: List[AssetRecord]
