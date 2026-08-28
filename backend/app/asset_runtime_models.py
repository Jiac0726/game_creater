from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.asset_workflow_models import AssetPackExportRequest, AssetPackExportResult


class CollisionMode(str, Enum):
    NONE = "none"
    BOX = "box"


class AssetRuntimeConfig(BaseModel):
    asset_id: str
    pivot_x: float = Field(default=0.5, ge=0.0, le=1.0)
    pivot_y: float = Field(default=1.0, ge=0.0, le=1.0)
    pixels_per_unit: float = Field(default=100.0, gt=0, le=10000)
    render_layer: str = "default"
    sorting_order: int = Field(default=0, ge=-32768, le=32767)
    collision_mode: CollisionMode = CollisionMode.NONE
    collision_is_trigger: bool = False
    gameplay_tags: list[str] = Field(default_factory=list)
    updated_at: str


class AssetRuntimeConfigPatch(BaseModel):
    pivot_x: float | None = Field(default=None, ge=0.0, le=1.0)
    pivot_y: float | None = Field(default=None, ge=0.0, le=1.0)
    pixels_per_unit: float | None = Field(default=None, gt=0, le=10000)
    render_layer: str | None = None
    sorting_order: int | None = Field(default=None, ge=-32768, le=32767)
    collision_mode: CollisionMode | None = None
    collision_is_trigger: bool | None = None
    gameplay_tags: list[str] | None = None


class BulkAssetRuntimeConfigPatch(BaseModel):
    asset_ids: list[str] = Field(min_length=1, max_length=500)
    patch: AssetRuntimeConfigPatch


class RuntimeAssetPackExportRequest(AssetPackExportRequest):
    include_runtime_config: bool = True


class RuntimeAssetPackExportResult(AssetPackExportResult):
    runtime_config_count: int = 0
