from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class ComposerExportTarget(str, Enum):
    GENERIC = "generic"
    GODOT4 = "godot4"
    UNITY2D = "unity2d"


class ComposerTransform(BaseModel):
    x: float = 0.0
    y: float = 0.0
    rotation_deg: float = 0.0
    scale_x: float = Field(default=1.0, ge=-100.0, le=100.0)
    scale_y: float = Field(default=1.0, ge=-100.0, le=100.0)


class ComposerLayerCreate(BaseModel):
    name: str
    y_sort: bool = False


class ComposerLayerPatch(BaseModel):
    name: str | None = None
    order: int | None = None
    visible: bool | None = None
    locked: bool | None = None
    y_sort: bool | None = None


class ComposerLayer(BaseModel):
    id: str
    name: str
    order: int
    visible: bool = True
    locked: bool = False
    y_sort: bool = False


class ComposerItemCreate(BaseModel):
    asset_id: str
    layer_id: str | None = None
    transform: ComposerTransform = Field(default_factory=ComposerTransform)
    z_index: int = Field(default=0, ge=-4096, le=4096)


class ComposerItemPatch(BaseModel):
    layer_id: str | None = None
    transform: ComposerTransform | None = None
    z_index: int | None = Field(default=None, ge=-4096, le=4096)
    visible: bool | None = None
    locked: bool | None = None


class ComposerItem(BaseModel):
    id: str
    asset_id: str
    asset_name: str
    image_url: str
    width: int
    height: int
    layer_id: str
    transform: ComposerTransform
    z_index: int = 0
    visible: bool = True
    locked: bool = False


class ComposerSceneCreate(BaseModel):
    name: str
    width: int = Field(default=1920, ge=1, le=32768)
    height: int = Field(default=1080, ge=1, le=32768)
    grid_size: int = Field(default=32, ge=1, le=1024)
    background: str = "#20242b"


class ComposerScenePatch(BaseModel):
    name: str | None = None
    width: int | None = Field(default=None, ge=1, le=32768)
    height: int | None = Field(default=None, ge=1, le=32768)
    grid_size: int | None = Field(default=None, ge=1, le=1024)
    background: str | None = None


class ComposerScene(BaseModel):
    id: str
    name: str
    width: int
    height: int
    grid_size: int
    background: str
    layers: list[ComposerLayer]
    items: list[ComposerItem]
    created_at: str
    updated_at: str


class ComposerExportRequest(BaseModel):
    target: ComposerExportTarget
    scene_id: str


class ComposerExportResult(BaseModel):
    scene_id: str
    target: ComposerExportTarget
    archive_path: str
    download_url: str
