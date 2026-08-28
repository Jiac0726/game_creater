from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.services.asset_library import LibraryAssetNotFoundError
from app.services.smart_asset_search import SmartAssetSearchService
from app.smart_asset_search_models import (
    SimilarAssetRequest,
    SmartAssetSearchRequest,
    SmartAssetSearchResponse,
    SmartSearchProviderStatus,
)


def build_smart_asset_search_router(workspace: str | Path) -> APIRouter:
    router = APIRouter(prefix="/library/smart-search", tags=["smart-asset-search"])
    service = SmartAssetSearchService(workspace)

    @router.get("/providers", response_model=list[SmartSearchProviderStatus])
    def providers() -> list[SmartSearchProviderStatus]:
        return service.providers()

    @router.post("/text", response_model=SmartAssetSearchResponse)
    def text_search(request: SmartAssetSearchRequest) -> SmartAssetSearchResponse:
        try:
            return service.search(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/similar", response_model=SmartAssetSearchResponse)
    def similar_search(request: SimilarAssetRequest) -> SmartAssetSearchResponse:
        try:
            return service.similar(request)
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return router
