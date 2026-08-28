from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.asset_intelligence_models import (
    AssetIntelligenceApplyRequest,
    AssetIntelligenceBulkRequest,
    AssetIntelligenceReport,
)
from app.asset_library_models import LibraryAsset
from app.services.asset_intelligence import AssetIntelligenceService
from app.services.asset_library import LibraryAssetNotFoundError


def build_asset_intelligence_router(workspace: str | Path) -> APIRouter:
    router = APIRouter(prefix="/library/intelligence", tags=["asset-intelligence"])
    service = AssetIntelligenceService(workspace)

    @router.get("/status")
    def status() -> dict:
        return service.status()

    @router.post("/assets/{asset_id}/analyze", response_model=AssetIntelligenceReport)
    def analyze(asset_id: str, duplicate_threshold: float = 0.90) -> AssetIntelligenceReport:
        try:
            return service.analyze(asset_id, duplicate_threshold=duplicate_threshold)
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/analyze-bulk", response_model=list[AssetIntelligenceReport])
    def analyze_bulk(request: AssetIntelligenceBulkRequest) -> list[AssetIntelligenceReport]:
        try:
            return service.analyze_bulk(request.asset_ids, duplicate_threshold=request.duplicate_threshold)
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/assets/{asset_id}/apply", response_model=LibraryAsset)
    def apply(asset_id: str, request: AssetIntelligenceApplyRequest) -> LibraryAsset:
        try:
            return service.apply(asset_id, request)
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
