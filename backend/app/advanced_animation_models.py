from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class FrameBoxType(str, Enum):
    HIT = "hit"
    HURT = "hurt"
    INTERACTION = "interaction"


class AnimationTransition(BaseModel):
    from_state: str
    to_state: str
    trigger: str = ""


class AnimationStateSetCreate(BaseModel):
    name: str
    states: dict[str, str] = Field(min_length=1, max_length=100)
    default_state: str
    directions: dict[str, str] = Field(default_factory=dict, max_length=16)
    transitions: list[AnimationTransition] = Field(default_factory=list, max_length=200)


class AnimationStateSetPatch(BaseModel):
    name: str | None = None
    states: dict[str, str] | None = None
    default_state: str | None = None
    directions: dict[str, str] | None = None
    transitions: list[AnimationTransition] | None = None


class AnimationStateSet(BaseModel):
    id: str
    name: str
    states: dict[str, str]
    default_state: str
    directions: dict[str, str]
    transitions: list[AnimationTransition]
    created_at: str
    updated_at: str


class AnimationEventCreate(BaseModel):
    clip_id: str
    frame_index: int = Field(ge=0)
    name: str
    payload: dict = Field(default_factory=dict)


class AnimationEvent(BaseModel):
    id: str
    clip_id: str
    frame_index: int
    name: str
    payload: dict
    created_at: str


class FrameBoxCreate(BaseModel):
    clip_id: str
    frame_index: int = Field(ge=0)
    box_type: FrameBoxType
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    width: float = Field(gt=0.0, le=1.0)
    height: float = Field(gt=0.0, le=1.0)


class FrameBox(BaseModel):
    id: str
    clip_id: str
    frame_index: int
    box_type: FrameBoxType
    x: float
    y: float
    width: float
    height: float
    created_at: str


class AdvancedAnimationExportRequest(BaseModel):
    state_set_ids: list[str] = Field(min_length=1, max_length=100)
    engine: str = Field(pattern="^(generic|godot4|unity2d)$")


class AdvancedAnimationExportResult(BaseModel):
    export_id: str
    engine: str
    state_set_count: int
    archive_path: str
    download_url: str
