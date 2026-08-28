from __future__ import annotations

from pydantic import BaseModel, Field

from app.asset_library_models import LibraryAsset, LibraryAssetVersion
from app.asset_workflow_models import AssetEditRequest


class BatchAssetEditRequest(BaseModel):
    asset_ids: list[str] = Field(min_length=1, max_length=500)
    edit: AssetEditRequest
    stop_on_error: bool = False


class BatchAssetEditItem(BaseModel):
    asset_id: str
    ok: bool
    version: int | None = None
    error: str | None = None


class BatchAssetEditResult(BaseModel):
    items: list[BatchAssetEditItem]
    succeeded: int
    failed: int


class ActivateAssetVersionResult(BaseModel):
    asset: LibraryAsset
    version: LibraryAssetVersion


class ReparentAssetsRequest(BaseModel):
    child_asset_ids: list[str] = Field(min_length=1, max_length=500)
    remove_existing_parents: bool = True


class ReparentAssetsResult(BaseModel):
    parent_asset_id: str
    child_asset_ids: list[str]
    removed_parent_links: int = 0


class PackPreflightRequest(BaseModel):
    asset_ids: list[str] = Field(default_factory=list, max_length=1000)
    collection_id: str | None = None
    require_reviewed: bool = True
    require_masks: bool = False
    require_alpha: bool = False


class PackPreflightIssue(BaseModel):
    level: str
    code: str
    asset_id: str | None = None
    message: str


class PackPreflightResult(BaseModel):
    valid: bool
    asset_count: int
    error_count: int
    warning_count: int
    issues: list[PackPreflightIssue] = Field(default_factory=list)


class BatchImportItem(BaseModel):
    filename: str
    ok: bool
    asset_id: str | None = None
    error: str | None = None


class BatchImportResult(BaseModel):
    items: list[BatchImportItem]
    imported: int
    failed: int
