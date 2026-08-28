from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from PIL import Image

from app.advanced_animation_models import (
    AdvancedAnimationExportRequest,
    AnimationEventCreate,
    AnimationStateSetCreate,
    FrameBoxCreate,
    FrameBoxType,
)
from app.asset_2d_models import AnimationClipCreateRequest
from app.main import app
from app.services.advanced_animation import AdvancedAnimationService
from app.services.ai_action_registry import AIActionRegistry
from app.services.asset_2d_resources import Asset2DResourceService
from app.services.asset_library_workflow import AssetLibraryWorkflowService
from app.services.pipeline import AssetSplitPipeline


def _setup(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GAME_CREATER_MODE", "mock")
    workspace = tmp_path / "workspace"
    pipeline = AssetSplitPipeline(workspace)
    workflow = AssetLibraryWorkflowService(workspace, pipeline)
    a_path = tmp_path / "a.png"; b_path = tmp_path / "b.png"
    Image.new("RGBA", (32, 48), (200, 50, 50, 255)).save(a_path)
    Image.new("RGBA", (32, 48), (220, 80, 80, 255)).save(b_path)
    a = workflow.import_image(a_path, name="Hero A", category="creatures")
    b = workflow.import_image(b_path, name="Hero B", category="creatures")
    resources = Asset2DResourceService(workspace)
    idle = resources.create_animation(AnimationClipCreateRequest(name="idle", frame_asset_ids=[a.id, b.id], fps=6, loop=True))
    walk = resources.create_animation(AnimationClipCreateRequest(name="walk", frame_asset_ids=[a.id, b.id, a.id], fps=10, loop=True))
    return workspace, idle, walk


def test_state_events_boxes_and_frame_validation(tmp_path: Path, monkeypatch) -> None:
    workspace, idle, walk = _setup(tmp_path, monkeypatch)
    service = AdvancedAnimationService(workspace)
    state_set = service.create_state_set(AnimationStateSetCreate(name="Player", states={"idle": idle.id, "walk": walk.id}, default_state="idle", directions={"right": walk.id}, transitions=[]))
    assert state_set.states["walk"] == walk.id
    event = service.add_event(AnimationEventCreate(clip_id=walk.id, frame_index=1, name="footstep", payload={"sound":"step"}))
    assert event.frame_index == 1
    box = service.add_frame_box(FrameBoxCreate(clip_id=walk.id, frame_index=2, box_type=FrameBoxType.HIT, x=.2, y=.2, width=.5, height=.5))
    assert box.box_type == FrameBoxType.HIT
    with pytest.raises(ValueError):
        service.add_event(AnimationEventCreate(clip_id=idle.id, frame_index=99, name="bad"))
    with pytest.raises(ValueError):
        service.add_frame_box(FrameBoxCreate(clip_id=walk.id, frame_index=0, box_type=FrameBoxType.HURT, x=.8, y=.8, width=.4, height=.4))


def test_advanced_animation_exports_engine_helpers(tmp_path: Path, monkeypatch) -> None:
    workspace, idle, walk = _setup(tmp_path, monkeypatch)
    service = AdvancedAnimationService(workspace)
    state_set = service.create_state_set(AnimationStateSetCreate(name="Player", states={"idle": idle.id, "walk": walk.id}, default_state="idle"))
    service.add_event(AnimationEventCreate(clip_id=walk.id, frame_index=1, name="footstep"))
    service.add_frame_box(FrameBoxCreate(clip_id=walk.id, frame_index=1, box_type=FrameBoxType.HURT, x=.1, y=.1, width=.8, height=.8))
    godot = service.export(AdvancedAnimationExportRequest(state_set_ids=[state_set.id], engine="godot4"))
    unity = service.export(AdvancedAnimationExportRequest(state_set_ids=[state_set.id], engine="unity2d"))
    with zipfile.ZipFile(godot.archive_path) as archive:
        assert "advanced_animation.json" in archive.namelist()
        assert "godot4/GameCreaterAdvancedAnimation.gd" in archive.namelist()
    with zipfile.ZipFile(unity.archive_path) as archive:
        names=set(archive.namelist())
        assert "unity2d/Assets/GameCreaterAdvancedAnimation/advanced_animation.json" in names
        assert "unity2d/Assets/GameCreaterAdvancedAnimation/Runtime/GameCreaterFrameBox.cs" in names


def test_advanced_animation_actions_are_ai_native() -> None:
    actions={item.action_id for item in AIActionRegistry(app).catalog().actions}
    required={
        "post.library.advanced.animation.state.sets",
        "post.library.advanced.animation.events",
        "post.library.advanced.animation.frame.boxes",
        "post.library.advanced.animation.export",
    }
    assert required.issubset(actions)
