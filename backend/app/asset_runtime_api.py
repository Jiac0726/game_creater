from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.asset_runtime_models import (
    AssetRuntimeConfig,
    AssetRuntimeConfigPatch,
    BulkAssetRuntimeConfigPatch,
    RuntimeAssetPackExportRequest,
    RuntimeAssetPackExportResult,
)
from app.services.asset_library import LibraryAssetNotFoundError
from app.services.asset_runtime_config import AssetRuntimeConfigService
from app.services.asset_runtime_pack import AssetRuntimePackService
from app.services.pipeline import AssetSplitPipeline


def build_asset_runtime_router(workspace: str | Path, pipeline: AssetSplitPipeline) -> APIRouter:
    router = APIRouter(prefix="/library", tags=["asset-runtime"])
    config_service = AssetRuntimeConfigService(workspace)
    pack_service = AssetRuntimePackService(workspace, pipeline)

    @router.get("/assets/{asset_id}/runtime-config", response_model=AssetRuntimeConfig)
    def get_runtime_config(asset_id: str) -> AssetRuntimeConfig:
        try:
            return config_service.get(asset_id)
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc

    @router.patch("/assets/{asset_id}/runtime-config", response_model=AssetRuntimeConfig)
    def patch_runtime_config(asset_id: str, patch: AssetRuntimeConfigPatch) -> AssetRuntimeConfig:
        try:
            return config_service.patch(asset_id, patch)
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/assets/bulk/runtime-config", response_model=list[AssetRuntimeConfig])
    def bulk_runtime_config(request: BulkAssetRuntimeConfigPatch) -> list[AssetRuntimeConfig]:
        try:
            return config_service.bulk_patch(request)
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/packs/export-runtime", response_model=RuntimeAssetPackExportResult)
    def export_runtime_pack(request: RuntimeAssetPackExportRequest) -> RuntimeAssetPackExportResult:
        try:
            return pack_service.export(request)
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
