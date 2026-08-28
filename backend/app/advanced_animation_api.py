from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.advanced_animation_models import (
    AdvancedAnimationExportRequest,
    AdvancedAnimationExportResult,
    AnimationEvent,
    AnimationEventCreate,
    AnimationStateSet,
    AnimationStateSetCreate,
    AnimationStateSetPatch,
    FrameBox,
    FrameBoxCreate,
)
from app.services.advanced_animation import AdvancedAnimationService, AnimationStateSetNotFoundError


def build_advanced_animation_router(workspace: str | Path) -> APIRouter:
    router = APIRouter(prefix="/library/advanced-animation", tags=["advanced-animation"])
    service = AdvancedAnimationService(workspace)

    @router.get("/state-sets", response_model=list[AnimationStateSet])
    def list_state_sets() -> list[AnimationStateSet]:
        return service.list_state_sets()

    @router.post("/state-sets", response_model=AnimationStateSet)
    def create_state_set(request: AnimationStateSetCreate) -> AnimationStateSet:
        try:
            return service.create_state_set(request)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/state-sets/{state_set_id}", response_model=AnimationStateSet)
    def get_state_set(state_set_id: str) -> AnimationStateSet:
        try:
            return service.get_state_set(state_set_id)
        except AnimationStateSetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Animation state set not found") from exc

    @router.patch("/state-sets/{state_set_id}", response_model=AnimationStateSet)
    def patch_state_set(state_set_id: str, request: AnimationStateSetPatch) -> AnimationStateSet:
        try:
            return service.patch_state_set(state_set_id, request)
        except AnimationStateSetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Animation state set not found") from exc
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/events", response_model=AnimationEvent)
    def add_event(request: AnimationEventCreate) -> AnimationEvent:
        try:
            return service.add_event(request)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/events/{clip_id}", response_model=list[AnimationEvent])
    def list_events(clip_id: str) -> list[AnimationEvent]:
        try:
            return service.list_events(clip_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Animation not found") from exc

    @router.delete("/events/{event_id}")
    def delete_event(event_id: str) -> dict:
        try:
            service.delete_event(event_id)
            return {"deleted": event_id}
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Event not found") from exc

    @router.post("/frame-boxes", response_model=FrameBox)
    def add_frame_box(request: FrameBoxCreate) -> FrameBox:
        try:
            return service.add_frame_box(request)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/frame-boxes/{clip_id}", response_model=list[FrameBox])
    def list_frame_boxes(clip_id: str) -> list[FrameBox]:
        try:
            return service.list_frame_boxes(clip_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Animation not found") from exc

    @router.delete("/frame-boxes/{box_id}")
    def delete_frame_box(box_id: str) -> dict:
        try:
            service.delete_frame_box(box_id)
            return {"deleted": box_id}
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Frame box not found") from exc

    @router.post("/export", response_model=AdvancedAnimationExportResult)
    def export(request: AdvancedAnimationExportRequest) -> AdvancedAnimationExportResult:
        try:
            return service.export(request)
        except (AnimationStateSetNotFoundError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/exports/{export_id}")
    def download_export(export_id: str) -> FileResponse:
        try:
            path = service.export_path(export_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Export not found") from exc
        return FileResponse(path, media_type="application/zip", filename=path.name)

    return router
