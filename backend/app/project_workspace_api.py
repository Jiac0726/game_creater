from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.project_workspace_models import (
    ProjectWorkspace,
    ProjectWorkspaceCreate,
    ProjectWorkspacePatch,
    WorkspaceAssetAddRequest,
    WorkspaceAssetBinding,
    WorkspaceAssetPatch,
    WorkspaceDependencyCreate,
    WorkspaceExportResult,
    WorkspaceResolution,
)
from app.services.asset_library import LibraryAssetNotFoundError
from app.services.project_workspace import (
    ProjectWorkspaceNotFoundError,
    ProjectWorkspaceService,
    WorkspaceAssetNotFoundError,
)


def build_project_workspace_router(workspace: str | Path) -> APIRouter:
    router = APIRouter(prefix="/library/project-workspaces", tags=["project-workspace"])
    service = ProjectWorkspaceService(workspace)

    @router.get("", response_model=list[ProjectWorkspace])
    def list_workspaces() -> list[ProjectWorkspace]:
        return service.list()

    @router.post("", response_model=ProjectWorkspace)
    def create_workspace(request: ProjectWorkspaceCreate) -> ProjectWorkspace:
        try:
            return service.create(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/{workspace_id}", response_model=ProjectWorkspace)
    def get_workspace(workspace_id: str) -> ProjectWorkspace:
        try:
            return service.get(workspace_id)
        except ProjectWorkspaceNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Project workspace not found") from exc

    @router.patch("/{workspace_id}", response_model=ProjectWorkspace)
    def patch_workspace(workspace_id: str, patch: ProjectWorkspacePatch) -> ProjectWorkspace:
        try:
            return service.patch(workspace_id, patch)
        except ProjectWorkspaceNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Project workspace not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/{workspace_id}/assets", response_model=ProjectWorkspace)
    def add_assets(workspace_id: str, request: WorkspaceAssetAddRequest) -> ProjectWorkspace:
        try:
            return service.add_assets(workspace_id, request)
        except ProjectWorkspaceNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Project workspace not found") from exc
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.patch("/{workspace_id}/assets/{asset_id}", response_model=WorkspaceAssetBinding)
    def patch_asset(workspace_id: str, asset_id: str, patch: WorkspaceAssetPatch) -> WorkspaceAssetBinding:
        try:
            return service.patch_asset(workspace_id, asset_id, patch)
        except ProjectWorkspaceNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Project workspace not found") from exc
        except WorkspaceAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Workspace asset not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.delete("/{workspace_id}/assets/{asset_id}", response_model=ProjectWorkspace)
    def remove_asset(workspace_id: str, asset_id: str) -> ProjectWorkspace:
        try:
            return service.remove_asset(workspace_id, asset_id)
        except ProjectWorkspaceNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Project workspace not found") from exc
        except WorkspaceAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Workspace asset not found") from exc

    @router.post("/{workspace_id}/dependencies", response_model=ProjectWorkspace)
    def add_dependency(workspace_id: str, request: WorkspaceDependencyCreate) -> ProjectWorkspace:
        try:
            return service.add_dependency(workspace_id, request)
        except ProjectWorkspaceNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Project workspace not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.delete("/{workspace_id}/dependencies/{source_asset_id}/{target_asset_id}", response_model=ProjectWorkspace)
    def remove_dependency(workspace_id: str, source_asset_id: str, target_asset_id: str) -> ProjectWorkspace:
        try:
            return service.remove_dependency(workspace_id, source_asset_id, target_asset_id)
        except ProjectWorkspaceNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Project workspace not found") from exc

    @router.get("/{workspace_id}/resolve", response_model=WorkspaceResolution)
    def resolve_workspace(workspace_id: str) -> WorkspaceResolution:
        try:
            return service.resolve(workspace_id)
        except ProjectWorkspaceNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Project workspace not found") from exc
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/{workspace_id}/export", response_model=WorkspaceExportResult)
    def export_workspace(workspace_id: str) -> WorkspaceExportResult:
        try:
            return service.export(workspace_id)
        except ProjectWorkspaceNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Project workspace not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get("/exports/{export_id}")
    def download_export(export_id: str) -> FileResponse:
        try:
            path = service.export_path(export_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Workspace export not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return FileResponse(path, media_type="application/zip", filename=f"{export_id}.zip")

    return router
