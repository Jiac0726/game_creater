from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AssetReviewState(str, Enum):
    GENERATED = "generated"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    PRODUCTION_READY = "production_ready"
    IN_USE = "in_use"
    ARCHIVED = "archived"


class AssetRelationType(str, Enum):
    PARENT_OF = "parent_of"
    VARIANT_OF = "variant_of"
    DERIVED_FROM = "derived_from"
    PART_OF = "part_of"
    RELATED_TO = "related_to"


class LibraryAssetPatch(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    review_state: Optional[AssetReviewState] = None
    favorite: Optional[bool] = None
    notes: Optional[str] = None
    tags: Optional[list[str]] = None


class BulkLibraryAssetPatch(BaseModel):
    asset_ids: list[str] = Field(min_length=1, max_length=500)
    review_state: Optional[AssetReviewState] = None
    favorite: Optional[bool] = None
    add_tags: list[str] = Field(default_factory=list)
    remove_tags: list[str] = Field(default_factory=list)


class CreateCollectionRequest(BaseModel):
    name: str
    description: str = ""


class CollectionMembershipRequest(BaseModel):
    asset_ids: list[str] = Field(min_length=1)


class AssetRelationRequest(BaseModel):
    target_asset_id: str
    relation_type: AssetRelationType = AssetRelationType.RELATED_TO


class LibraryAssetVersion(BaseModel):
    version: int
    kind: str
    image_path: str
    mask_path: Optional[str] = None
    alpha_path: Optional[str] = None
    created_at: str
    metadata: dict = Field(default_factory=dict)


class LibraryAsset(BaseModel):
    id: str
    scene_id: str
    scene_asset_id: str
    project_id: Optional[str] = None
    name: str
    category: str = "uncategorized"
    subcategory: str = ""
    review_state: AssetReviewState = AssetReviewState.NEEDS_REVIEW
    favorite: bool = False
    confidence: float = 0.0
    asset_score: float = 0.0
    width: int = 0
    height: int = 0
    image_path: str
    mask_path: str
    alpha_path: Optional[str] = None
    source_image_path: Optional[str] = None
    completed: bool = False
    active_version: int = 1
    notes: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    collections: list[str] = Field(default_factory=list)
    provenance: dict = Field(default_factory=dict)
    created_at: str
    updated_at: str


class AssetLibraryStats(BaseModel):
    total_assets: int = 0
    needs_review: int = 0
    approved: int = 0
    production_ready: int = 0
    completed_by_ai: int = 0
    favorites: int = 0
    collections: int = 0
    categories: dict[str, int] = Field(default_factory=dict)


class AssetSearchResult(BaseModel):
    items: list[LibraryAsset]
    total: int
    limit: int
    offset: int
