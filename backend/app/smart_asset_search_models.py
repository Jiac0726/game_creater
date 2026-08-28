from __future__ import annotations

from pydantic import BaseModel, Field

from app.asset_library_models import LibraryAsset


class SmartAssetSearchRequest(BaseModel):
    query: str
    limit: int = Field(default=24, ge=1, le=100)
    category: str | None = None
    min_asset_score: float | None = Field(default=None, ge=0.0, le=1.0)


class SimilarAssetRequest(BaseModel):
    asset_id: str
    limit: int = Field(default=24, ge=1, le=100)
    include_metadata_similarity: bool = True


class SmartAssetSearchHit(BaseModel):
    asset: LibraryAsset
    score: float = Field(ge=0.0, le=1.0)
    image_url: str
    reasons: list[str] = Field(default_factory=list)


class SmartAssetSearchResponse(BaseModel):
    query: str
    expanded_terms: list[str] = Field(default_factory=list)
    hits: list[SmartAssetSearchHit]
    providers: list[str] = Field(default_factory=list)


class SmartSearchProviderStatus(BaseModel):
    id: str
    ready: bool
    kind: str
    description: str
