from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.asset_2d_models import (
    AnimationClip,
    AnimationClipCreateRequest,
    AnimationClipPatch,
    AnimationFrameSequenceRequest,
    CollisionPolygon,
    CollisionPolygonGenerateRequest,
    CollisionPolygonPatch,
    GameReadyPackExportRequest,
    GameReadyPackExportResult,
    TileSetCreateRequest,
    TileSetDefinition,
    TileSetPatch,
)
from app.services.asset_2d_pack import Asset2DGameReadyPackService
from app.services.asset_2d_resources import Asset2DResourceService
from app.services.asset_library import LibraryAssetNotFoundError
from app.services.pipeline import AssetSplitPipeline


def build_asset_2d_router(workspace: str | Path, pipeline: AssetSplitPipeline) -> APIRouter:
    router = APIRouter(prefix="/library", tags=["asset-2d-resources"])
    resources = Asset2DResourceService(workspace)
    packs = Asset2DGameReadyPackService(workspace, pipeline)

    @router.get("/assets/{asset_id}/collision-polygon", response_model=CollisionPolygon | None)
    def get_collision_polygon(asset_id: str) -> CollisionPolygon | None:
        try:
            return resources.get_polygon(asset_id)
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc

    @router.patch("/assets/{asset_id}/collision-polygon", response_model=CollisionPolygon)
    def patch_collision_polygon(asset_id: str, patch: CollisionPolygonPatch) -> CollisionPolygon:
        try:
            return resources.set_polygon(asset_id, patch)
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/assets/{asset_id}/collision-polygon/generate", response_model=CollisionPolygon)
    def generate_collision_polygon(
        asset_id: str,
        request: CollisionPolygonGenerateRequest,
    ) -> CollisionPolygon:
        try:
            return resources.generate_polygon(asset_id, request)
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/animations", response_model=list[AnimationClip])
    def list_animations() -> list[AnimationClip]:
        return resources.list_animations()

    @router.post("/animations", response_model=AnimationClip)
    def create_animation(request: AnimationClipCreateRequest) -> AnimationClip:
        try:
            return resources.create_animation(request)
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/animations/{clip_id}", response_model=AnimationClip)
    def get_animation(clip_id: str) -> AnimationClip:
        try:
            return resources.get_animation(clip_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Animation not found") from exc

    @router.patch("/animations/{clip_id}", response_model=AnimationClip)
    def patch_animation(clip_id: str, patch: AnimationClipPatch) -> AnimationClip:
        try:
            return resources.patch_animation(clip_id, patch)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Animation not found") from exc
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.put("/animations/{clip_id}/frames", response_model=AnimationClip)
    def set_animation_frames(clip_id: str, request: AnimationFrameSequenceRequest) -> AnimationClip:
        try:
            return resources.set_animation_frames(clip_id, request)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Animation not found") from exc
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/tilesets", response_model=list[TileSetDefinition])
    def list_tilesets() -> list[TileSetDefinition]:
        return resources.list_tilesets()

    @router.post("/tilesets", response_model=TileSetDefinition)
    def create_tileset(request: TileSetCreateRequest) -> TileSetDefinition:
        try:
            return resources.create_tileset(request)
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/tilesets/{tileset_id}", response_model=TileSetDefinition)
    def get_tileset(tileset_id: str) -> TileSetDefinition:
        try:
            return resources.get_tileset(tileset_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="TileSet not found") from exc

    @router.patch("/tilesets/{tileset_id}", response_model=TileSetDefinition)
    def patch_tileset(tileset_id: str, patch: TileSetPatch) -> TileSetDefinition:
        try:
            return resources.patch_tileset(tileset_id, patch)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="TileSet not found") from exc
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/packs/export-game-ready", response_model=GameReadyPackExportResult)
    def export_game_ready_pack(request: GameReadyPackExportRequest) -> GameReadyPackExportResult:
        try:
            return packs.export(request)
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
