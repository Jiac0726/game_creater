from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.asset_library_models import LibraryAssetNotFoundError
from app.asset_workflow_maintenance_models import (
    ActivateAssetVersionResult,
    BatchAssetEditRequest,
    BatchAssetEditResult,
    BatchImportItem,
    BatchImportResult,
    PackPreflightRequest,
    PackPreflightResult,
    ReparentAssetsRequest,
    ReparentAssetsResult,
)
from app.services.asset_library_maintenance import AssetLibraryMaintenanceService
from app.services.asset_library_workflow import AssetLibraryWorkflowService
from app.services.pipeline import AssetSplitPipeline


SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def build_asset_workflow_maintenance_router(
    workspace: str | Path,
    pipeline: AssetSplitPipeline,
) -> APIRouter:
    router = APIRouter(prefix="/library", tags=["asset-library-workflow"])
    workspace_path = Path(workspace)
    workflow = AssetLibraryWorkflowService(workspace_path, pipeline)
    maintenance = AssetLibraryMaintenanceService(workspace_path, pipeline)
    upload_root = workspace_path / "uploads" / "library_batch"
    upload_root.mkdir(parents=True, exist_ok=True)

    @router.post("/import/images", response_model=BatchImportResult)
    def import_images(
        images: list[UploadFile] = File(...),
        category: str = Form("uncategorized"),
        tags: str = Form(""),
    ) -> BatchImportResult:
        if not images:
            raise HTTPException(status_code=400, detail="At least one image is required")
        if len(images) > 200:
            raise HTTPException(status_code=400, detail="A batch can contain at most 200 images")
        tag_list = [item.strip() for item in tags.split(",") if item.strip()]
        items: list[BatchImportItem] = []
        for upload in images:
            filename = upload.filename or "asset.png"
            suffix = Path(filename).suffix.lower()
            if suffix not in SUPPORTED_IMAGE_SUFFIXES:
                items.append(
                    BatchImportItem(
                        filename=filename,
                        ok=False,
                        error="Unsupported format; use PNG, JPG, JPEG or WEBP",
                    )
                )
                continue
            temp_path = upload_root / f"{uuid4().hex}{suffix}"
            try:
                with temp_path.open("wb") as output:
                    shutil.copyfileobj(upload.file, output)
                name = Path(filename).stem.strip() or "asset"
                asset = workflow.import_image(
                    temp_path,
                    name=name,
                    category=category,
                    tags=tag_list,
                    original_filename=filename,
                )
                items.append(BatchImportItem(filename=filename, ok=True, asset_id=asset.id))
            except Exception as exc:
                items.append(BatchImportItem(filename=filename, ok=False, error=str(exc)))
            finally:
                temp_path.unlink(missing_ok=True)
        imported = sum(1 for item in items if item.ok)
        return BatchImportResult(items=items, imported=imported, failed=len(items) - imported)

    @router.post(
        "/assets/{asset_id}/versions/{version}/activate",
        response_model=ActivateAssetVersionResult,
    )
    def activate_asset_version(asset_id: str, version: int) -> ActivateAssetVersionResult:
        if version < 1:
            raise HTTPException(status_code=400, detail="Version must be >= 1")
        try:
            return maintenance.activate_version(asset_id, version)
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/assets/bulk/edit", response_model=BatchAssetEditResult)
    def bulk_edit_assets(request: BatchAssetEditRequest) -> BatchAssetEditResult:
        try:
            return maintenance.bulk_edit(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post(
        "/assets/{parent_asset_id}/reparent",
        response_model=ReparentAssetsResult,
    )
    def reparent_assets(
        parent_asset_id: str,
        request: ReparentAssetsRequest,
    ) -> ReparentAssetsResult:
        try:
            return maintenance.reparent(parent_asset_id, request)
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/packs/preflight", response_model=PackPreflightResult)
    def pack_preflight(request: PackPreflightRequest) -> PackPreflightResult:
        try:
            return maintenance.preflight(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
