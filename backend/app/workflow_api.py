from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.completion_models import AssetCompletionRequest, AssetCompletionResult
from app.services.completion_providers import CompletionError
from app.services.completion_service import CompletionService
from app.services.generation_providers import ImageGenerationError
from app.services.pipeline import AssetSplitPipeline
from app.services.project_store import ProjectNotFoundError
from app.services.scene_store import AssetNotFoundError, SceneNotFoundError
from app.services.workflow_manager import WorkflowManager
from app.workflow_models import ProjectRecord, RunProjectRequest, RunProjectResponse

PROJECT_ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")
SCENE_ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")


def build_workflow_router(workspace: str | Path, pipeline: AssetSplitPipeline) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["workflow"])
    manager = WorkflowManager(workspace, pipeline)
    completion = CompletionService(workspace, pipeline)

    @router.get("/generation/providers")
    def generation_providers() -> dict:
        return {"providers": manager.provider_catalog()}

    @router.get("/completion/providers")
    def completion_providers() -> dict:
        return {"providers": completion.health()}

    @router.post("/projects/run", response_model=RunProjectResponse)
    def run_project(request: RunProjectRequest) -> RunProjectResponse:
        try:
            project = manager.run(request)
            return RunProjectResponse(project=project)
        except ImageGenerationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/projects/{project_id}", response_model=ProjectRecord)
    def get_project(project_id: str) -> ProjectRecord:
        _validate_project_id(project_id)
        try:
            return manager.load(project_id)
        except ProjectNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Project not found") from exc

    @router.post(
        "/scenes/{scene_id}/assets/{asset_id}/complete",
        response_model=AssetCompletionResult,
    )
    def complete_asset(
        scene_id: str,
        asset_id: str,
        request: AssetCompletionRequest,
    ) -> AssetCompletionResult:
        _validate_scene_id(scene_id)
        try:
            return completion.complete(scene_id, asset_id, request)
        except SceneNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Scene not found") from exc
        except AssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Asset not found") from exc
        except CompletionError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router


def _validate_project_id(project_id: str) -> None:
    if not PROJECT_ID_PATTERN.fullmatch(project_id):
        raise HTTPException(status_code=400, detail="Invalid project id")


def _validate_scene_id(scene_id: str) -> None:
    if not SCENE_ID_PATTERN.fullmatch(scene_id):
        raise HTTPException(status_code=400, detail="Invalid scene id")
