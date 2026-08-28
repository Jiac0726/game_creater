from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.engine_sync_models import (
    EngineSyncPlan,
    EngineSyncProfile,
    EngineSyncProfileCreate,
    EngineSyncProfilePatch,
    EngineSyncPruneRequest,
    EngineSyncPruneResult,
    EngineSyncResult,
)
from app.services.asset_library import LibraryAssetNotFoundError
from app.services.engine_sync import EngineSyncProfileNotFoundError, EngineSyncService


def build_engine_sync_router(workspace: str | Path) -> APIRouter:
    router = APIRouter(prefix="/library/engine-sync", tags=["engine-sync"])
    service = EngineSyncService(workspace)

    @router.get("/profiles", response_model=list[EngineSyncProfile])
    def list_profiles() -> list[EngineSyncProfile]:
        return service.list()

    @router.post("/profiles", response_model=EngineSyncProfile)
    def create_profile(request: EngineSyncProfileCreate) -> EngineSyncProfile:
        try:
            return service.create(request)
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/profiles/{profile_id}", response_model=EngineSyncProfile)
    def get_profile(profile_id: str) -> EngineSyncProfile:
        try:
            return service.get(profile_id)
        except EngineSyncProfileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Sync profile not found") from exc

    @router.patch("/profiles/{profile_id}", response_model=EngineSyncProfile)
    def patch_profile(profile_id: str, patch: EngineSyncProfilePatch) -> EngineSyncProfile:
        try:
            return service.patch(profile_id, patch)
        except EngineSyncProfileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Sync profile not found") from exc
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/profiles/{profile_id}/plan", response_model=EngineSyncPlan)
    def sync_plan(profile_id: str) -> EngineSyncPlan:
        try:
            return service.plan(profile_id)
        except EngineSyncProfileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Sync profile not found") from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/profiles/{profile_id}/sync", response_model=EngineSyncResult)
    def apply_sync(profile_id: str) -> EngineSyncResult:
        try:
            return service.sync(profile_id)
        except EngineSyncProfileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Sync profile not found") from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.delete("/profiles/{profile_id}/stale", response_model=EngineSyncPruneResult)
    def prune_stale(profile_id: str, request: EngineSyncPruneRequest) -> EngineSyncPruneResult:
        try:
            return service.prune(profile_id, request.relative_paths)
        except EngineSyncProfileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Sync profile not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
