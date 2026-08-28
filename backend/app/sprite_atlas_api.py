from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services.asset_library import LibraryAssetNotFoundError
from app.services.sprite_atlas import SpriteAtlasService
from app.sprite_atlas_models import AtlasBuildRequest, AtlasBuildResult


def build_sprite_atlas_router(workspace: str | Path) -> APIRouter:
    router = APIRouter(prefix="/library/atlases", tags=["sprite-atlas"])
    service = SpriteAtlasService(workspace)

    @router.post("", response_model=AtlasBuildResult)
    def build(request: AtlasBuildRequest) -> AtlasBuildResult:
        try:
            return service.build(request)
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.get("/{atlas_id}/download")
    def download(atlas_id: str) -> FileResponse:
        try:
            path = service.download_path(atlas_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Atlas not found") from exc
        return FileResponse(path, media_type="application/zip", filename=path.name)

    return router
