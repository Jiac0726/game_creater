from __future__ import annotations

from pydantic import BaseModel, Field


class AssetPackDependency(BaseModel):
    pack_id: str
    version: str | None = None


class AssetPackCreateRequest(BaseModel):
    name: str
    description: str = ""
    asset_ids: list[str] = Field(min_length=1, max_length=5000)
    dependencies: list[AssetPackDependency] = Field(default_factory=list, max_length=100)


class AssetPackUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    asset_ids: list[str] | None = Field(default=None, min_length=1, max_length=5000)
    dependencies: list[AssetPackDependency] | None = Field(default=None, max_length=100)


class AssetPackReleaseRequest(BaseModel):
    version: str
    notes: str = ""


class AssetPackInstallRequest(BaseModel):
    version: str | None = None


class AssetPackAssetLock(BaseModel):
    asset_id: str
    version: int
    name: str
    image_path: str
    mask_path: str | None = None
    alpha_path: str | None = None


class AssetPackRelease(BaseModel):
    pack_id: str
    version: str
    notes: str = ""
    assets: list[AssetPackAssetLock]
    dependencies: list[AssetPackDependency]
    created_at: str


class AssetPackDefinition(BaseModel):
    id: str
    name: str
    description: str = ""
    asset_ids: list[str]
    dependencies: list[AssetPackDependency]
    latest_version: str | None = None
    created_at: str
    updated_at: str


class AssetPackInstallation(BaseModel):
    pack_id: str
    version: str
    installed_at: str
    lock: dict = Field(default_factory=dict)


class AssetPackUpdateInfo(BaseModel):
    pack_id: str
    installed_version: str
    latest_version: str
    update_available: bool


class AssetPackExportResult(BaseModel):
    export_id: str
    pack_id: str
    version: str
    archive_path: str
    download_url: str
