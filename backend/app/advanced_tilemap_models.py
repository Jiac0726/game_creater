from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class TileMapLayerType(str, Enum):
    VISUAL = "visual"
    COLLISION = "collision"
    NAVIGATION = "navigation"


class TileMapCell(BaseModel):
    x: int
    y: int
    asset_id: str | None = None
    terrain: str | None = None


class TileMapLayerCreate(BaseModel):
    name: str
    layer_type: TileMapLayerType = TileMapLayerType.VISUAL


class TileMapLayer(BaseModel):
    id: str
    name: str
    layer_type: TileMapLayerType
    order: int
    visible: bool = True
    cells: list[TileMapCell] = Field(default_factory=list)


class TileMapCreateRequest(BaseModel):
    name: str
    tileset_id: str
    width: int = Field(default=64, ge=1, le=2048)
    height: int = Field(default=64, ge=1, le=2048)


class TileMapProject(BaseModel):
    id: str
    name: str
    tileset_id: str
    width: int
    height: int
    layers: list[TileMapLayer]
    created_at: str
    updated_at: str


class TileCoordinate(BaseModel):
    x: int
    y: int


class TileMapPaintRequest(BaseModel):
    layer_id: str
    cells: list[TileCoordinate] = Field(min_length=1, max_length=10000)
    asset_id: str | None = None
    terrain: str | None = None


class TileMapEraseRequest(BaseModel):
    layer_id: str
    cells: list[TileCoordinate] = Field(min_length=1, max_length=10000)


class TileMapExportRequest(BaseModel):
    engine: str = Field(pattern="^(generic|godot4|unity2d)$")


class TileMapExportResult(BaseModel):
    export_id: str
    map_id: str
    engine: str
    archive_path: str
    download_url: str
