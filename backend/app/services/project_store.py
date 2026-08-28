from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.workflow_models import ProjectRecord, WorkflowEvent, WorkflowStage


class ProjectNotFoundError(FileNotFoundError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProjectStore:
    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace)
        self.projects_root = self.workspace / "projects"
        self.projects_root.mkdir(parents=True, exist_ok=True)

    def project_dir(self, project_id: str) -> Path:
        return self.projects_root / project_id

    def create(self, project_id: str, concept: str) -> ProjectRecord:
        now = utc_now()
        record = ProjectRecord(
            project_id=project_id,
            concept=concept,
            stage=WorkflowStage.CREATED,
            created_at=now,
            updated_at=now,
        )
        self.project_dir(project_id).mkdir(parents=True, exist_ok=False)
        self.save(record)
        return record

    def load(self, project_id: str) -> ProjectRecord:
        path = self.project_dir(project_id) / "project.json"
        if not path.is_file():
            raise ProjectNotFoundError(project_id)
        return ProjectRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, record: ProjectRecord) -> ProjectRecord:
        record.updated_at = utc_now()
        path = self.project_dir(record.project_id) / "project.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return record

    def event(
        self,
        record: ProjectRecord,
        stage: WorkflowStage,
        message: str,
        *,
        status: str = "ok",
        data: dict | None = None,
    ) -> ProjectRecord:
        record.stage = stage
        record.events.append(
            WorkflowEvent(
                stage=stage,
                status=status,
                message=message,
                created_at=utc_now(),
                data=data or {},
            )
        )
        return self.save(record)
