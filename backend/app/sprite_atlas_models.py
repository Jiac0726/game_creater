from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class AtlasEngine(str, Enum):
    GENERIC = "generic"
    GODOT4 = "godot4"
    UNITY2D = "unity2d"


class AtlasBuildRequest(BaseModel):
    name: str
    asset_ids: list[str] = Field(min_length=1, max_length=2000)
    engine: AtlasEngine = AtlasEngine.GENERIC
    max_width: int = Field(default=2048, ge=64, le=16384)
    max_height: int = Field(default=2048, ge=64, le=16384)
    padding: int = Field(default=2, ge=0, le=64)
    trim_transparent: bool = True
    power_of_two: bool = True


class AtlasSpriteEntry(BaseModel):
    asset_id: str
    asset_name: str
    page: int
    x: int
    y: int
    width: int
    height: int
    source_width: int
    source_height: int
    trim_x: int = 0
    trim_y: int = 0


class AtlasPage(BaseModel):
    index: int
    filename: str
    width: int
    height: int
    sprite_count: int


class AtlasManifest(BaseModel):
    schema: str = "game-creater/sprite-atlas/v1"
    atlas_id: str
    name: str
    engine: AtlasEngine
    padding: int
    trim_transparent: bool
    power_of_two: bool
    pages: list[AtlasPage]
    sprites: list[AtlasSpriteEntry]


class AtlasBuildResult(BaseModel):
    atlas_id: str
    name: str
    engine: AtlasEngine
    page_count: int
    sprite_count: int
    archive_path: str
    manifest_path: str
    download_url: str
