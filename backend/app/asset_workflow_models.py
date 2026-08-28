from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.models import BBox


class LibrarySplitMode(str, Enum):
    GRID = "grid"
    ALPHA_COMPONENTS = "alpha_components"
    AI_SCENE = "ai_scene"


class LibrarySplitRequest(BaseModel):
    mode: LibrarySplitMode
    rows: int = Field(default=1, ge=1, le=64)
    columns: int = Field(default=1, ge=1, le=64)
    min_area: int = Field(default=64, ge=1)
    prompts: list[str] = Field(default_factory=list)
    name_prefix: str | None = None
    category: str | None = None


class LibrarySplitResult(BaseModel):
    parent_asset_id: str
    mode: LibrarySplitMode
    child_asset_ids: list[str] = Field(default_factory=list)
    scene_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class HierarchyChildrenRequest(BaseModel):
    child_asset_ids: list[str] = Field(min_length=1, max_length=500)


class HierarchyNode(BaseModel):
    asset_id: str
    name: str
    category: str
    image_path: str
    children: list["HierarchyNode"] = Field(default_factory=list)


class AssetEditOperation(str, Enum):
    CROP = "crop"
    RESIZE = "resize"
    TRIM_ALPHA = "trim_alpha"
    FLIP_HORIZONTAL = "flip_horizontal"
    FLIP_VERTICAL = "flip_vertical"
    ROTATE_90 = "rotate_90"
    PAD = "pad"


class AssetEditRequest(BaseModel):
    operation: AssetEditOperation
    rect: BBox | None = None
    width: int | None = Field(default=None, ge=1, le=16384)
    height: int | None = Field(default=None, ge=1, le=16384)
    padding: int = Field(default=0, ge=0, le=2048)
    clockwise: bool = True
    activate: bool = True


class AssetEditResult(BaseModel):
    asset_id: str
    operation: AssetEditOperation
    version: int
    image_path: str
    mask_path: str | None = None
    alpha_path: str | None = None
    width: int
    height: int


class AssetPackEngine(str, Enum):
    GENERIC = "generic"
    GODOT4 = "godot4"
    UNITY2D = "unity2d"


class AssetPackExportRequest(BaseModel):
    name: str
    asset_ids: list[str] = Field(default_factory=list, max_length=1000)
    collection_id: str | None = None
    engine: AssetPackEngine = AssetPackEngine.GENERIC
    include_masks: bool = True
    include_alpha: bool = True
    include_hierarchy: bool = True


class AssetPackExportResult(BaseModel):
    pack_id: str
    name: str
    engine: AssetPackEngine
    asset_count: int
    archive_path: str
    download_url: str
    manifest_path: str
