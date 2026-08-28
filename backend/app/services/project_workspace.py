from __future__ import annotations

import json
import re
import sqlite3
import zipfile
from collections import deque
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from app.project_workspace_models import (
    ProjectWorkspace,
    ProjectWorkspaceCreate,
    ProjectWorkspacePatch,
    WorkspaceAssetAddRequest,
    WorkspaceAssetBinding,
    WorkspaceAssetPatch,
    WorkspaceDependency,
    WorkspaceDependencyCreate,
    WorkspaceEngine,
    WorkspaceExportResult,
    WorkspaceResolution,
    WorkspaceResolvedAsset,
)
from app.services.asset_library import AssetLibrary, utc_now


class ProjectWorkspaceNotFoundError(KeyError):
    pass


class WorkspaceAssetNotFoundError(KeyError):
    pass


class ProjectWorkspaceService:
    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace)
        self.library = AssetLibrary(self.workspace)
        self.state_dir = self.workspace.parent / ".game_creater_state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.state_dir / "project_workspace.db"
        self.export_root = self.state_dir / "project_workspace_exports"
        self.export_root.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _init_schema(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS project_workspaces (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    engine TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS project_workspace_assets (
                    workspace_id TEXT NOT NULL,
                    asset_id TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT '',
                    locked_version INTEGER,
                    follows_active INTEGER NOT NULL DEFAULT 0,
                    added_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(workspace_id, asset_id),
                    FOREIGN KEY(workspace_id) REFERENCES project_workspaces(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS project_workspace_dependencies (
                    workspace_id TEXT NOT NULL,
                    source_asset_id TEXT NOT NULL,
                    target_asset_id TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(workspace_id, source_asset_id, target_asset_id),
                    FOREIGN KEY(workspace_id) REFERENCES project_workspaces(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_workspace_assets_ws ON project_workspace_assets(workspace_id);
                CREATE INDEX IF NOT EXISTS idx_workspace_deps_ws ON project_workspace_dependencies(workspace_id);
                """
            )

    def create(self, request: ProjectWorkspaceCreate) -> ProjectWorkspace:
        name = request.name.strip()
        if not name:
            raise ValueError("Workspace name cannot be empty")
        workspace_id = f"gproj_{uuid4().hex[:12]}"
        now = utc_now()
        with self._connect() as db:
            db.execute(
                "INSERT INTO project_workspaces(id,name,engine,description,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                (workspace_id, name, request.engine.value, request.description.strip(), now, now),
            )
        return self.get(workspace_id)

    def list(self) -> list[ProjectWorkspace]:
        with self._connect() as db:
            ids = [row["id"] for row in db.execute("SELECT id FROM project_workspaces ORDER BY updated_at DESC,id").fetchall()]
        return [self.get(workspace_id) for workspace_id in ids]

    def get(self, workspace_id: str) -> ProjectWorkspace:
        with self._connect() as db:
            row = db.execute("SELECT * FROM project_workspaces WHERE id=?", (workspace_id,)).fetchone()
            if row is None:
                raise ProjectWorkspaceNotFoundError(workspace_id)
            asset_rows = db.execute(
                "SELECT * FROM project_workspace_assets WHERE workspace_id=? ORDER BY added_at,asset_id",
                (workspace_id,),
            ).fetchall()
            dep_rows = db.execute(
                "SELECT * FROM project_workspace_dependencies WHERE workspace_id=? ORDER BY created_at,source_asset_id,target_asset_id",
                (workspace_id,),
            ).fetchall()
        assets = [
            WorkspaceAssetBinding(
                asset_id=item["asset_id"],
                role=item["role"],
                locked_version=item["locked_version"],
                follows_active=bool(item["follows_active"]),
                added_at=item["added_at"],
                updated_at=item["updated_at"],
            )
            for item in asset_rows
        ]
        dependencies = [
            WorkspaceDependency(
                source_asset_id=item["source_asset_id"],
                target_asset_id=item["target_asset_id"],
                reason=item["reason"],
                created_at=item["created_at"],
            )
            for item in dep_rows
        ]
        return ProjectWorkspace(
            id=row["id"],
            name=row["name"],
            engine=WorkspaceEngine(row["engine"]),
            description=row["description"],
            assets=assets,
            dependencies=dependencies,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def patch(self, workspace_id: str, patch: ProjectWorkspacePatch) -> ProjectWorkspace:
        current = self.get(workspace_id)
        name = current.name if patch.name is None else patch.name.strip()
        if not name:
            raise ValueError("Workspace name cannot be empty")
        engine = current.engine if patch.engine is None else patch.engine
        description = current.description if patch.description is None else patch.description.strip()
        with self._connect() as db:
            db.execute(
                "UPDATE project_workspaces SET name=?,engine=?,description=?,updated_at=? WHERE id=?",
                (name, engine.value, description, utc_now(), workspace_id),
            )
        return self.get(workspace_id)

    def _touch(self, workspace_id: str) -> None:
        with self._connect() as db:
            db.execute("UPDATE project_workspaces SET updated_at=? WHERE id=?", (utc_now(), workspace_id))

    def add_assets(self, workspace_id: str, request: WorkspaceAssetAddRequest) -> ProjectWorkspace:
        self.get(workspace_id)
        role = request.role.strip()
        asset_ids = list(dict.fromkeys(item.strip() for item in request.asset_ids if item.strip()))
        if not asset_ids:
            raise ValueError("At least one asset is required")
        now = utc_now()
        resolved: list[tuple[str, int | None, int]] = []
        for asset_id in asset_ids:
            asset = self.library.get(asset_id)
            locked = asset.active_version if request.lock_to_current else None
            resolved.append((asset_id, locked, 0 if request.lock_to_current else 1))
        with self._connect() as db:
            for asset_id, locked, follows_active in resolved:
                db.execute(
                    """
                    INSERT INTO project_workspace_assets(workspace_id,asset_id,role,locked_version,follows_active,added_at,updated_at)
                    VALUES (?,?,?,?,?,?,?)
                    ON CONFLICT(workspace_id,asset_id) DO UPDATE SET
                      role=excluded.role,locked_version=excluded.locked_version,follows_active=excluded.follows_active,updated_at=excluded.updated_at
                    """,
                    (workspace_id, asset_id, role, locked, follows_active, now, now),
                )
        self._touch(workspace_id)
        return self.get(workspace_id)

    def patch_asset(self, workspace_id: str, asset_id: str, patch: WorkspaceAssetPatch) -> WorkspaceAssetBinding:
        project = self.get(workspace_id)
        current = next((item for item in project.assets if item.asset_id == asset_id), None)
        if current is None:
            raise WorkspaceAssetNotFoundError(asset_id)
        role = current.role if patch.role is None else patch.role.strip()
        locked_version = current.locked_version
        follows_active = current.follows_active
        if patch.follow_active is True:
            follows_active = True
            locked_version = None
        elif patch.follow_active is False:
            follows_active = False
            if patch.locked_version is None:
                locked_version = self.library.get(asset_id).active_version
        if patch.locked_version is not None:
            versions = {item.version for item in self.library.list_versions(asset_id)}
            if patch.locked_version not in versions:
                raise ValueError(f"Asset version does not exist: {asset_id} v{patch.locked_version}")
            locked_version = patch.locked_version
            follows_active = False
        with self._connect() as db:
            db.execute(
                "UPDATE project_workspace_assets SET role=?,locked_version=?,follows_active=?,updated_at=? WHERE workspace_id=? AND asset_id=?",
                (role, locked_version, int(follows_active), utc_now(), workspace_id, asset_id),
            )
        self._touch(workspace_id)
        return next(item for item in self.get(workspace_id).assets if item.asset_id == asset_id)

    def remove_asset(self, workspace_id: str, asset_id: str) -> ProjectWorkspace:
        project = self.get(workspace_id)
        if not any(item.asset_id == asset_id for item in project.assets):
            raise WorkspaceAssetNotFoundError(asset_id)
        with self._connect() as db:
            db.execute(
                "DELETE FROM project_workspace_dependencies WHERE workspace_id=? AND (source_asset_id=? OR target_asset_id=?)",
                (workspace_id, asset_id, asset_id),
            )
            db.execute(
                "DELETE FROM project_workspace_assets WHERE workspace_id=? AND asset_id=?",
                (workspace_id, asset_id),
            )
        self._touch(workspace_id)
        return self.get(workspace_id)

    def add_dependency(self, workspace_id: str, request: WorkspaceDependencyCreate) -> ProjectWorkspace:
        project = self.get(workspace_id)
        source = request.source_asset_id.strip()
        target = request.target_asset_id.strip()
        if source == target:
            raise ValueError("An asset cannot depend on itself")
        members = {item.asset_id for item in project.assets}
        if source not in members or target not in members:
            raise ValueError("Both dependency endpoints must already belong to the workspace")
        proposed = list(project.dependencies) + [
            WorkspaceDependency(source_asset_id=source, target_asset_id=target, reason=request.reason.strip(), created_at=utc_now())
        ]
        self._dependency_order(members, proposed)
        now = utc_now()
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO project_workspace_dependencies(workspace_id,source_asset_id,target_asset_id,reason,created_at) VALUES (?,?,?,?,?)",
                (workspace_id, source, target, request.reason.strip(), now),
            )
        self._touch(workspace_id)
        return self.get(workspace_id)

    def remove_dependency(self, workspace_id: str, source_asset_id: str, target_asset_id: str) -> ProjectWorkspace:
        self.get(workspace_id)
        with self._connect() as db:
            db.execute(
                "DELETE FROM project_workspace_dependencies WHERE workspace_id=? AND source_asset_id=? AND target_asset_id=?",
                (workspace_id, source_asset_id, target_asset_id),
            )
        self._touch(workspace_id)
        return self.get(workspace_id)

    @staticmethod
    def _dependency_order(members: set[str], dependencies: list[WorkspaceDependency]) -> list[str]:
        indegree = {asset_id: 0 for asset_id in members}
        dependents: dict[str, list[str]] = {asset_id: [] for asset_id in members}
        for dependency in dependencies:
            if dependency.source_asset_id not in members or dependency.target_asset_id not in members:
                continue
            indegree[dependency.source_asset_id] += 1
            dependents[dependency.target_asset_id].append(dependency.source_asset_id)
        queue = deque(sorted(asset_id for asset_id, degree in indegree.items() if degree == 0))
        order: list[str] = []
        while queue:
            asset_id = queue.popleft()
            order.append(asset_id)
            for dependent in sorted(dependents[asset_id]):
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    queue.append(dependent)
        if len(order) != len(members):
            raise ValueError("Workspace asset dependency cycle detected")
        return order

    def resolve(self, workspace_id: str) -> WorkspaceResolution:
        project = self.get(workspace_id)
        resolved: list[WorkspaceResolvedAsset] = []
        drift_count = 0
        for binding in project.assets:
            asset = self.library.get(binding.asset_id)
            versions = {item.version: item for item in self.library.list_versions(binding.asset_id)}
            if binding.follows_active:
                resolved_version = asset.active_version
            else:
                if binding.locked_version is None:
                    raise ValueError(f"Locked workspace asset has no version: {binding.asset_id}")
                resolved_version = binding.locked_version
            version = versions.get(resolved_version)
            if version is None:
                raise ValueError(f"Workspace references missing asset version: {binding.asset_id} v{resolved_version}")
            drifted = not binding.follows_active and resolved_version != asset.active_version
            drift_count += int(drifted)
            resolved.append(
                WorkspaceResolvedAsset(
                    asset_id=asset.id,
                    name=asset.name,
                    role=binding.role,
                    locked_version=binding.locked_version,
                    active_version=asset.active_version,
                    resolved_version=resolved_version,
                    follows_active=binding.follows_active,
                    drifted=drifted,
                    image_path=version.image_path,
                    mask_path=version.mask_path,
                    alpha_path=version.alpha_path,
                )
            )
        order = self._dependency_order({item.asset_id for item in project.assets}, project.dependencies)
        by_id = {item.asset_id: item for item in resolved}
        ordered = [by_id[asset_id] for asset_id in order if asset_id in by_id]
        return WorkspaceResolution(workspace_id=workspace_id, assets=ordered, dependency_order=order, drift_count=drift_count)

    def export(self, workspace_id: str) -> WorkspaceExportResult:
        project = self.get(workspace_id)
        resolution = self.resolve(workspace_id)
        export_id = f"gprojexp_{uuid4().hex[:12]}"
        root = self.export_root / export_id
        root.mkdir(parents=True, exist_ok=False)
        (root / "project.json").write_text(project.model_dump_json(indent=2), encoding="utf-8")
        lock = {
            "schema": "game-creater/project-workspace-lock/v1",
            "workspace_id": workspace_id,
            "engine": project.engine.value,
            "dependency_order": resolution.dependency_order,
            "assets": [item.model_dump(mode="json") for item in resolution.assets],
        }
        (root / "project.lock.json").write_text(json.dumps(lock, ensure_ascii=False, indent=2), encoding="utf-8")
        archive = self.export_root / f"{export_id}.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as out:
            out.write(root / "project.json", "project.json")
            out.write(root / "project.lock.json", "project.lock.json")
        return WorkspaceExportResult(
            export_id=export_id,
            workspace_id=workspace_id,
            archive_path=str(archive),
            download_url=f"/api/v1/library/project-workspaces/exports/{export_id}",
        )

    def export_path(self, export_id: str) -> Path:
        if not re.fullmatch(r"gprojexp_[0-9a-f]{12}", export_id):
            raise ValueError("Invalid workspace export id")
        path = self.export_root / f"{export_id}.zip"
        if not path.is_file():
            raise FileNotFoundError(path)
        return path
