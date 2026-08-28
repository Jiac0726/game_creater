from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse

from app.asset_pack_models import (
    AssetPackCreateRequest,
    AssetPackDefinition,
    AssetPackExportResult,
    AssetPackInstallRequest,
    AssetPackInstallation,
    AssetPackRelease,
    AssetPackReleaseRequest,
    AssetPackUpdateInfo,
    AssetPackUpdateRequest,
)
from app.services.asset_pack_system import (
    AssetPackNotFoundError,
    AssetPackReleaseNotFoundError,
    AssetPackSystemService,
)


def build_asset_pack_router(workspace: str | Path) -> APIRouter:
    router = APIRouter(prefix="/library/package-system", tags=["asset-pack-system"])
    service = AssetPackSystemService(workspace)

    @router.get("/packs", response_model=list[AssetPackDefinition])
    def list_packs() -> list[AssetPackDefinition]:
        return service.list()

    @router.post("/packs", response_model=AssetPackDefinition)
    def create_pack(request: AssetPackCreateRequest) -> AssetPackDefinition:
        try:
            return service.create(request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Asset or dependency pack not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/packs/{pack_id}", response_model=AssetPackDefinition)
    def get_pack(pack_id: str) -> AssetPackDefinition:
        try:
            return service.get(pack_id)
        except AssetPackNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Pack not found") from exc

    @router.patch("/packs/{pack_id}", response_model=AssetPackDefinition)
    def update_pack(pack_id: str, request: AssetPackUpdateRequest) -> AssetPackDefinition:
        try:
            return service.update(pack_id, request)
        except AssetPackNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Pack not found") from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Asset or dependency pack not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/packs/{pack_id}/releases", response_model=list[AssetPackRelease])
    def list_releases(pack_id: str) -> list[AssetPackRelease]:
        try:
            return service.list_releases(pack_id)
        except AssetPackNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Pack not found") from exc

    @router.post("/packs/{pack_id}/releases", response_model=AssetPackRelease)
    def release_pack(pack_id: str, request: AssetPackReleaseRequest) -> AssetPackRelease:
        try:
            return service.release(pack_id, request)
        except AssetPackNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Pack not found") from exc
        except (AssetPackReleaseNotFoundError, KeyError) as exc:
            raise HTTPException(status_code=404, detail="Dependency release or asset not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/packs/{pack_id}/install", response_model=AssetPackInstallation)
    def install_pack(pack_id: str, request: AssetPackInstallRequest) -> AssetPackInstallation:
        try:
            return service.install(pack_id, request.version)
        except (AssetPackNotFoundError, AssetPackReleaseNotFoundError) as exc:
            raise HTTPException(status_code=404, detail="Pack or release not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.delete("/packs/{pack_id}/install", status_code=204)
    def uninstall_pack(pack_id: str) -> Response:
        service.uninstall(pack_id)
        return Response(status_code=204)

    @router.get("/installed", response_model=list[AssetPackInstallation])
    def installed_packs() -> list[AssetPackInstallation]:
        return service.list_installations()

    @router.get("/updates", response_model=list[AssetPackUpdateInfo])
    def pack_updates() -> list[AssetPackUpdateInfo]:
        return service.updates()

    @router.post("/packs/{pack_id}/export", response_model=AssetPackExportResult)
    def export_pack(pack_id: str, request: AssetPackInstallRequest) -> AssetPackExportResult:
        try:
            return service.export_release(pack_id, request.version)
        except (AssetPackNotFoundError, AssetPackReleaseNotFoundError) as exc:
            raise HTTPException(status_code=404, detail="Pack or release not found") from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/exports/{export_id}")
    def download_pack(export_id: str) -> FileResponse:
        try:
            path = service.export_path(export_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Pack export not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return FileResponse(path, media_type="application/zip", filename=f"{export_id}.zip")

    return router
