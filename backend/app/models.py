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
    asset_score: float = 0.0
    score_components: dict[str, float] = Field(default_factory=dict)
    bbox: BBox
    image: str
    mask: str
    source_position: dict = Field(default_factory=dict)
    completed: bool = False
    notes: Optional[str] = None


class AssetPatch(BaseModel):
    label: Optional[str] = None
    category: Optional[str] = None
    notes: Optional[str] = None


class AssetMergeRequest(BaseModel):
    asset_ids: List[str]
    label: str = "merged_asset"
    category: Optional[str] = None
    notes: Optional[str] = None
    keep_sources: bool = False


class AssetSplitRequest(BaseModel):
    rect: BBox
    inside_label: Optional[str] = None
    outside_label: Optional[str] = None


class SceneManifest(BaseModel):
    scene_id: str
    source_image: str
    width: int
    height: int
    mode: str
    prompts: List[str]
    assets: List[AssetRecord]
    preview_image: Optional[str] = None
    source_file: Optional[str] = None


class SemanticExpandRequest(BaseModel):
    keyword: str
    depth: int = 2
    max_per_group: int = 12


class SemanticKeyword(BaseModel):
    zh: str
    en: str
    score: float
    source: str


class SemanticGroup(BaseModel):
    key: str
    label_zh: str
    items: List[SemanticKeyword]


class SemanticExpansion(BaseModel):
    input: str
    matched_concept: Optional[str] = None
    matched_concept_label: Optional[str] = None
    modifiers: List[str] = Field(default_factory=list)
    groups: List[SemanticGroup] = Field(default_factory=list)
    detection_prompts: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
