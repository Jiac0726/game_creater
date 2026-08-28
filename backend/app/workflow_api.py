from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.services.generation_providers import ImageGenerationError
from app.services.pipeline import AssetSplitPipeline
from app.services.project_store import ProjectNotFoundError
from app.services.workflow_manager import WorkflowManager
from app.workflow_models import ProjectRecord, RunProjectRequest, RunProjectResponse

PROJECT_ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")


def build_workflow_router(workspace: str | Path, pipeline: AssetSplitPipeline) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["workflow"])
    manager = WorkflowManager(workspace, pipeline)

    @router.get("/generation/providers")
    def generation_providers() -> dict:
        return {"providers": manager.provider_catalog()}

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

    return router


def _validate_project_id(project_id: str) -> None:
    if not PROJECT_ID_PATTERN.fullmatch(project_id):
        raise HTTPException(status_code=400, detail="Invalid project id")
