from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.advanced_tilemap_models import (
    TileMapCreateRequest,
    TileMapEraseRequest,
    TileMapExportRequest,
    TileMapExportResult,
    TileMapLayerCreate,
    TileMapPaintRequest,
    TileMapProject,
)
from app.services.advanced_tilemap import (
    AdvancedTileMapService,
    TileMapLayerNotFoundError,
    TileMapNotFoundError,
)


def build_advanced_tilemap_router(workspace: str | Path) -> APIRouter:
    router = APIRouter(prefix="/library/tilemaps", tags=["advanced-tilemap"])
    service = AdvancedTileMapService(workspace)

    @router.get("", response_model=list[TileMapProject])
    def list_tilemaps() -> list[TileMapProject]:
        return service.list()

    @router.post("", response_model=TileMapProject)
    def create_tilemap(request: TileMapCreateRequest) -> TileMapProject:
        try:
            return service.create(request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="TileSet not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/{map_id}", response_model=TileMapProject)
    def get_tilemap(map_id: str) -> TileMapProject:
        try:
            return service.get(map_id)
        except TileMapNotFoundError as exc:
            raise HTTPException(status_code=404, detail="TileMap not found") from exc

    @router.post("/{map_id}/layers", response_model=TileMapProject)
    def add_layer(map_id: str, request: TileMapLayerCreate) -> TileMapProject:
        try:
            return service.add_layer(map_id, request)
        except TileMapNotFoundError as exc:
            raise HTTPException(status_code=404, detail="TileMap not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/{map_id}/paint", response_model=TileMapProject)
    def paint_tilemap(map_id: str, request: TileMapPaintRequest) -> TileMapProject:
        try:
            return service.paint(map_id, request)
        except TileMapNotFoundError as exc:
            raise HTTPException(status_code=404, detail="TileMap not found") from exc
        except TileMapLayerNotFoundError as exc:
            raise HTTPException(status_code=404, detail="TileMap layer not found") from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Referenced asset or TileSet not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/{map_id}/erase", response_model=TileMapProject)
    def erase_tilemap(map_id: str, request: TileMapEraseRequest) -> TileMapProject:
        try:
            return service.erase(map_id, request)
        except TileMapNotFoundError as exc:
            raise HTTPException(status_code=404, detail="TileMap not found") from exc
        except TileMapLayerNotFoundError as exc:
            raise HTTPException(status_code=404, detail="TileMap layer not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/{map_id}/export", response_model=TileMapExportResult)
    def export_tilemap(map_id: str, request: TileMapExportRequest) -> TileMapExportResult:
        try:
            return service.export(map_id, request)
        except TileMapNotFoundError as exc:
            raise HTTPException(status_code=404, detail="TileMap not found") from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/exports/{export_id}")
    def download_tilemap_export(export_id: str) -> FileResponse:
        try:
            path = service.export_path(export_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="TileMap export not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return FileResponse(path, media_type="application/zip", filename=f"{export_id}.zip")

    return router
