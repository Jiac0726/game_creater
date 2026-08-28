from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.scene_composer_models import (
    ComposerExportResult,
    ComposerExportTarget,
    ComposerItemCreate,
    ComposerItemPatch,
    ComposerLayerCreate,
    ComposerLayerPatch,
    ComposerScene,
    ComposerSceneCreate,
    ComposerScenePatch,
)
from app.services.asset_library import LibraryAssetNotFoundError
from app.services.scene_composer import (
    ComposerItemNotFoundError,
    ComposerLayerNotFoundError,
    ComposerSceneNotFoundError,
    SceneComposerService,
)


def build_scene_composer_router(workspace: str | Path) -> APIRouter:
    router = APIRouter(prefix="/library/composer", tags=["scene-composer"])
    service = SceneComposerService(workspace)

    def fail(exc: Exception):
        if isinstance(exc, (ComposerSceneNotFoundError, ComposerLayerNotFoundError, ComposerItemNotFoundError, LibraryAssetNotFoundError, FileNotFoundError)):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if isinstance(exc, ValueError):
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        raise exc

    @router.get("/scenes", response_model=list[ComposerScene])
    def list_scenes() -> list[ComposerScene]:
        return service.list_scenes()

    @router.post("/scenes", response_model=ComposerScene)
    def create_scene(request: ComposerSceneCreate) -> ComposerScene:
        try:
            return service.create_scene(request)
        except Exception as exc:
            fail(exc)

    @router.get("/scenes/{scene_id}", response_model=ComposerScene)
    def get_scene(scene_id: str) -> ComposerScene:
        try:
            return service.get_scene(scene_id)
        except Exception as exc:
            fail(exc)

    @router.patch("/scenes/{scene_id}", response_model=ComposerScene)
    def patch_scene(scene_id: str, request: ComposerScenePatch) -> ComposerScene:
        try:
            return service.patch_scene(scene_id, request)
        except Exception as exc:
            fail(exc)

    @router.post("/scenes/{scene_id}/layers", response_model=ComposerScene)
    def add_layer(scene_id: str, request: ComposerLayerCreate) -> ComposerScene:
        try:
            return service.add_layer(scene_id, request)
        except Exception as exc:
            fail(exc)

    @router.patch("/scenes/{scene_id}/layers/{layer_id}", response_model=ComposerScene)
    def patch_layer(scene_id: str, layer_id: str, request: ComposerLayerPatch) -> ComposerScene:
        try:
            return service.patch_layer(scene_id, layer_id, request)
        except Exception as exc:
            fail(exc)

    @router.post("/scenes/{scene_id}/items", response_model=ComposerScene)
    def add_item(scene_id: str, request: ComposerItemCreate) -> ComposerScene:
        try:
            return service.add_item(scene_id, request)
        except Exception as exc:
            fail(exc)

    @router.patch("/scenes/{scene_id}/items/{item_id}", response_model=ComposerScene)
    def patch_item(scene_id: str, item_id: str, request: ComposerItemPatch) -> ComposerScene:
        try:
            return service.patch_item(scene_id, item_id, request)
        except Exception as exc:
            fail(exc)

    @router.delete("/scenes/{scene_id}/items/{item_id}", response_model=ComposerScene)
    def delete_item(scene_id: str, item_id: str) -> ComposerScene:
        try:
            return service.delete_item(scene_id, item_id)
        except Exception as exc:
            fail(exc)

    @router.post("/scenes/{scene_id}/export/{target}", response_model=ComposerExportResult)
    def export_scene(scene_id: str, target: ComposerExportTarget) -> ComposerExportResult:
        try:
            return service.export(scene_id, target)
        except Exception as exc:
            fail(exc)

    @router.get("/exports/{scene_id}/{target}")
    def download_export(scene_id: str, target: ComposerExportTarget) -> FileResponse:
        try:
            path = service.export_path(scene_id, target)
        except Exception as exc:
            fail(exc)
        return FileResponse(path, media_type="application/zip", filename=path.name)

    return router
