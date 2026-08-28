from __future__ import annotations

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


class AnimationClip(BaseModel):
    id: str
    name: str
    frame_asset_ids: list[str]
    fps: float
    loop: bool
    created_at: str
    updated_at: str


class TileSetCreateRequest(BaseModel):
    name: str
    tile_asset_ids: list[str] = Field(min_length=1, max_length=1000)
    tile_width: int = Field(default=32, ge=1, le=4096)
    tile_height: int = Field(default=32, ge=1, le=4096)
    terrain_tags: list[str] = Field(default_factory=list, max_length=100)


class TileSetPatch(BaseModel):
    name: str | None = None
    tile_asset_ids: list[str] | None = Field(default=None, min_length=1, max_length=1000)
    tile_width: int | None = Field(default=None, ge=1, le=4096)
    tile_height: int | None = Field(default=None, ge=1, le=4096)
    terrain_tags: list[str] | None = Field(default=None, max_length=100)


class TileSetDefinition(BaseModel):
    id: str
    name: str
    tile_asset_ids: list[str]
    tile_width: int
    tile_height: int
    terrain_tags: list[str]
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
