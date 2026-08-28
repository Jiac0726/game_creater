from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class EngineSyncEngine(str, Enum):
    GODOT4 = "godot4"
    UNITY2D = "unity2d"


class EngineSyncProfileCreate(BaseModel):
    name: str
    engine: EngineSyncEngine
    project_root: str
    asset_ids: list[str] = Field(min_length=1, max_length=5000)


class EngineSyncProfilePatch(BaseModel):
    name: str | None = None
    project_root: str | None = None
    asset_ids: list[str] | None = Field(default=None, min_length=1, max_length=5000)


class EngineSyncProfile(BaseModel):
    id: str
    name: str
    engine: EngineSyncEngine
    project_root: str
    managed_root: str
    asset_ids: list[str]
    created_at: str
    updated_at: str


class EngineSyncFile(BaseModel):
    relative_path: str
    source_path: str | None = None
    source_sha256: str | None = None
    target_sha256: str | None = None
    action: str = Field(pattern="^(add|update|unchanged|stale)$")


class EngineSyncPlan(BaseModel):
    profile_id: str
    engine: EngineSyncEngine
    managed_root: str
    files: list[EngineSyncFile]
    stale_paths: list[str]
    add_count: int = 0
    update_count: int = 0
    unchanged_count: int = 0


class EngineSyncResult(BaseModel):
    profile_id: str
    copied: list[str]
    unchanged: list[str]
    manifest_path: str
    synced_at: str


class EngineSyncPruneRequest(BaseModel):
    relative_paths: list[str] = Field(min_length=1, max_length=5000)


class EngineSyncPruneResult(BaseModel):
    profile_id: str
    removed: list[str]
