from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.asset_library_models import LibraryAsset
from app.asset_workflow_models import (
    AssetEditRequest,
    AssetEditResult,
    AssetPackExportRequest,
    AssetPackExportResult,
    HierarchyChildrenRequest,
    HierarchyNode,
    LibrarySplitRequest,
    LibrarySplitResult,
)
from app.services.asset_library import LibraryAssetNotFoundError
from app.services.asset_library_workflow import AssetLibraryWorkflowService
from app.services.pipeline import AssetSplitPipeline


def build_asset_workflow_router(workspace: str | Path, pipeline: AssetSplitPipeline) -> APIRouter:
    router = APIRouter(prefix="/library", tags=["asset-library-workflow"])
    workspace_path = Path(workspace)
    service = AssetLibraryWorkflowService(workspace_path, pipeline)
    upload_root = workspace_path / "uploads" / "library"
    upload_root.mkdir(parents=True, exist_ok=True)

    @router.post("/import/image", response_model=LibraryAsset)
    def import_image(
        image: UploadFile = File(...),
        name: str = Form(...),
        category: str = Form("uncategorized"),
        tags: str = Form(""),
    ) -> LibraryAsset:
        suffix = Path(image.filename or "asset.png").suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise HTTPException(status_code=400, detail="Supported formats: PNG, JPG, JPEG, WEBP")
        temp_path = upload_root / f"{uuid4().hex}{suffix}"
        try:
            with temp_path.open("wb") as output:
                shutil.copyfileobj(image.file, output)
            return service.import_image(
                temp_path,
                name=name,
                category=category,
                tags=[item.strip() for item in tags.split(",") if item.strip()],
                original_filename=image.filename,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            temp_path.unlink(missing_ok=True)

    @router.post("/assets/{asset_id}/split", response_model=LibrarySplitResult)
    def split_asset(asset_id: str, request: LibrarySplitRequest) -> LibrarySplitResult:
        try:
            return service.split(asset_id, request)
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/assets/{asset_id}/hierarchy", response_model=HierarchyNode)
    def hierarchy(asset_id: str, depth: int = Query(default=8, ge=0, le=32)) -> HierarchyNode:
        try:
            return service.hierarchy(asset_id, depth=depth)
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc

    @router.post("/assets/{asset_id}/children", response_model=HierarchyNode)
    def add_children(asset_id: str, request: HierarchyChildrenRequest) -> HierarchyNode:
        try:
            service.add_children(asset_id, request.child_asset_ids)
            return service.hierarchy(asset_id)
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.delete("/assets/{asset_id}/children/{child_asset_id}")
    def remove_child(asset_id: str, child_asset_id: str) -> dict:
        try:
            service.library.get(asset_id)
            service.library.get(child_asset_id)
            service.remove_child(asset_id, child_asset_id)
            return {"ok": True, "parent_asset_id": asset_id, "child_asset_id": child_asset_id}
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc

    @router.post("/assets/{asset_id}/edit", response_model=AssetEditResult)
    def edit_asset(asset_id: str, request: AssetEditRequest) -> AssetEditResult:
        try:
            return service.edit(asset_id, request)
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/packs/export", response_model=AssetPackExportResult)
    def export_pack(request: AssetPackExportRequest) -> AssetPackExportResult:
        try:
            return service.export_pack(request)
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/packs/{pack_id}/download")
    def download_pack(pack_id: str) -> FileResponse:
        try:
            archive = service.pack_archive(pack_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Asset pack not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return FileResponse(
            archive,
            media_type="application/zip",
            filename=f"{pack_id}.zip",
        )

    return router
