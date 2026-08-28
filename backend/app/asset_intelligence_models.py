from __future__ import annotations

from pydantic import BaseModel, Field


class AssetQualityMetric(BaseModel):
    key: str
    value: float
    score: float = Field(ge=0.0, le=1.0)
    note: str = ""


class DuplicateCandidate(BaseModel):
    asset_id: str
    name: str
    visual_similarity: float = Field(ge=0.0, le=1.0)


class AssetIntelligenceReport(BaseModel):
    asset_id: str
    suggested_category: str
    suggested_subcategory: str = ""
    suggested_tags: list[str] = Field(default_factory=list)
    quality_score: float = Field(ge=0.0, le=1.0)
    quality_metrics: list[AssetQualityMetric] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    duplicate_candidates: list[DuplicateCandidate] = Field(default_factory=list)


class AssetIntelligenceBulkRequest(BaseModel):
    asset_ids: list[str] = Field(min_length=1, max_length=500)
    duplicate_threshold: float = Field(default=0.90, ge=0.5, le=1.0)


class AssetIntelligenceApplyRequest(BaseModel):
    apply_category: bool = True
    apply_subcategory: bool = True
    add_tags: bool = True
    report: AssetIntelligenceReport
