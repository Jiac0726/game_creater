from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.asset_runtime_models import RuntimeAssetPackExportRequest, RuntimeAssetPackExportResult


class CollisionPoint(BaseModel):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)


class CollisionPolygon(BaseModel):
    asset_id: str
    points: list[CollisionPoint] = Field(min_length=3, max_length=128)
    source: str = "manual"
    updated_at: str


class CollisionPolygonPatch(BaseModel):
    points: list[CollisionPoint] = Field(min_length=3, max_length=128)


class CollisionPolygonGenerateRequest(BaseModel):
    alpha_threshold: int = Field(default=1, ge=0, le=255)
    max_points: int = Field(default=24, ge=3, le=128)


class AnimationClipCreateRequest(BaseModel):
    name: str
    frame_asset_ids: list[str] = Field(min_length=1, max_length=500)
    fps: float = Field(default=8.0, gt=0.0, le=120.0)
    loop: bool = True


class AnimationClipPatch(BaseModel):
    name: str | None = None
    frame_asset_ids: list[str] | None = Field(default=None, min_length=1, max_length=500)
    fps: float | None = Field(default=None, gt=0.0, le=120.0)
    loop: bool | None = None


class AnimationFrameSequenceRequest(BaseModel):
    frame_asset_ids: list[str] = Field(min_length=1, max_length=500)
    require_same_frames: bool = True


class AnimationClip(BaseModel):
    id: str
    name: str
    frame_asset_ids: list[str]
    fps: float
    loop: bool
    created_at: str
    updated_at: str


class AutoTileMode(str, Enum):
    NONE = "none"
    CARDINAL4 = "cardinal4"
    EIGHT8 = "eight8"


class TileTerrainRule(BaseModel):
    asset_id: str
    terrain: str
    neighbor_mask: int = Field(default=0, ge=0, le=255)
    priority: int = Field(default=0, ge=-1000, le=1000)


class TileSetCreateRequest(BaseModel):
    name: str
    tile_asset_ids: list[str] = Field(min_length=1, max_length=1000)
    tile_width: int = Field(default=32, ge=1, le=4096)
    tile_height: int = Field(default=32, ge=1, le=4096)
    terrain_tags: list[str] = Field(default_factory=list, max_length=100)
    autotile_mode: AutoTileMode = AutoTileMode.NONE
    terrain_rules: list[TileTerrainRule] = Field(default_factory=list, max_length=1000)


class TileSetPatch(BaseModel):
    name: str | None = None
    tile_asset_ids: list[str] | None = Field(default=None, min_length=1, max_length=1000)
    tile_width: int | None = Field(default=None, ge=1, le=4096)
    tile_height: int | None = Field(default=None, ge=1, le=4096)
    terrain_tags: list[str] | None = Field(default=None, max_length=100)
    autotile_mode: AutoTileMode | None = None
    terrain_rules: list[TileTerrainRule] | None = Field(default=None, max_length=1000)


class TileSetDefinition(BaseModel):
    id: str
    name: str
    tile_asset_ids: list[str]
    tile_width: int
    tile_height: int
    terrain_tags: list[str]
    autotile_mode: AutoTileMode = AutoTileMode.NONE
    terrain_rules: list[TileTerrainRule] = Field(default_factory=list)
    created_at: str
    updated_at: str


class GameReadyPackExportRequest(RuntimeAssetPackExportRequest):
    animation_ids: list[str] = Field(default_factory=list, max_length=100)
    tileset_ids: list[str] = Field(default_factory=list, max_length=100)
    include_collision_polygons: bool = True


class GameReadyPackExportResult(RuntimeAssetPackExportResult):
    animation_count: int = 0
    tileset_count: int = 0
    polygon_collision_count: int = 0
