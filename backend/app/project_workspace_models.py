from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class WorkspaceEngine(str, Enum):
    GENERIC = "generic"
    GODOT4 = "godot4"
    UNITY2D = "unity2d"


class ProjectWorkspaceCreate(BaseModel):
    name: str
    engine: WorkspaceEngine = WorkspaceEngine.GENERIC
    description: str = ""


class ProjectWorkspacePatch(BaseModel):
    name: str | None = None
    engine: WorkspaceEngine | None = None
    description: str | None = None


class WorkspaceAssetAddRequest(BaseModel):
    asset_ids: list[str] = Field(min_length=1, max_length=5000)
    lock_to_current: bool = True
    role: str = ""


class WorkspaceAssetPatch(BaseModel):
    role: str | None = None
    locked_version: int | None = Field(default=None, ge=1)
    follow_active: bool | None = None


class WorkspaceAssetBinding(BaseModel):
    asset_id: str
    role: str = ""
    locked_version: int | None = None
    follows_active: bool = False
    added_at: str
    updated_at: str


class WorkspaceDependencyCreate(BaseModel):
    source_asset_id: str
    target_asset_id: str
    reason: str = ""


class WorkspaceDependency(BaseModel):
    source_asset_id: str
    target_asset_id: str
    reason: str = ""
    created_at: str


class ProjectWorkspace(BaseModel):
    id: str
    name: str
    engine: WorkspaceEngine
    description: str = ""
    assets: list[WorkspaceAssetBinding] = Field(default_factory=list)
    dependencies: list[WorkspaceDependency] = Field(default_factory=list)
    created_at: str
    updated_at: str


class WorkspaceResolvedAsset(BaseModel):
    asset_id: str
    name: str
    role: str = ""
    locked_version: int | None = None
    active_version: int
    resolved_version: int
    follows_active: bool
    drifted: bool
    image_path: str
    mask_path: str | None = None
    alpha_path: str | None = None


class WorkspaceResolution(BaseModel):
    workspace_id: str
    assets: list[WorkspaceResolvedAsset]
    dependency_order: list[str]
    drift_count: int = 0


class WorkspaceExportResult(BaseModel):
    export_id: str
    workspace_id: str
    archive_path: str
    download_url: str
