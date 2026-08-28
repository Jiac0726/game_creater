from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from app.engine_sync_models import (
    EngineSyncEngine,
    EngineSyncFile,
    EngineSyncPlan,
    EngineSyncProfile,
    EngineSyncProfileCreate,
    EngineSyncProfilePatch,
    EngineSyncPruneResult,
    EngineSyncResult,
)
from app.services.asset_library import AssetLibrary, utc_now
from app.services.asset_runtime_config import AssetRuntimeConfigService


class EngineSyncProfileNotFoundError(KeyError):
    pass


class EngineSyncService:
    MANIFEST_NAME = "game_creater_manifest.json"

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace)
        self.library = AssetLibrary(self.workspace)
        self.runtime = AssetRuntimeConfigService(self.workspace)
        self.state_dir = self.workspace.parent / ".game_creater_state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.state_dir / "engine_sync.db"
        self._init_schema()

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
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
                CREATE TABLE IF NOT EXISTS engine_sync_profiles (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    engine TEXT NOT NULL,
                    project_root TEXT NOT NULL,
                    asset_ids_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS engine_sync_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id TEXT NOT NULL,
                    copied_count INTEGER NOT NULL,
                    unchanged_count INTEGER NOT NULL,
                    synced_at TEXT NOT NULL,
                    FOREIGN KEY(profile_id) REFERENCES engine_sync_profiles(id) ON DELETE CASCADE
                );
                """
            )

    @staticmethod
    def _normalize_asset_ids(asset_ids: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for raw in asset_ids:
            asset_id = raw.strip()
            if asset_id and asset_id not in seen:
                seen.add(asset_id)
                result.append(asset_id)
        if not result:
            raise ValueError("Sync profile must contain at least one asset")
        return result

    def _validate_assets(self, asset_ids: list[str]) -> list[str]:
        normalized = self._normalize_asset_ids(asset_ids)
        for asset_id in normalized:
            self.library.get(asset_id)
        return normalized

    @staticmethod
    def _validate_project_root(engine: EngineSyncEngine, raw_root: str) -> Path:
        if not raw_root.strip():
            raise ValueError("Project root cannot be empty")
        root = Path(raw_root).expanduser().resolve()
        if not root.is_dir():
            raise ValueError("Project root does not exist")
        if engine == EngineSyncEngine.GODOT4:
            if not (root / "project.godot").is_file():
                raise ValueError("Godot project root must contain project.godot")
        elif engine == EngineSyncEngine.UNITY2D:
            if not (root / "Assets").is_dir() or not (root / "ProjectSettings").is_dir():
                raise ValueError("Unity project root must contain Assets/ and ProjectSettings/")
        return root

    @staticmethod
    def _managed_relative(engine: EngineSyncEngine) -> Path:
        return Path("GameCreaterAssets") if engine == EngineSyncEngine.GODOT4 else Path("Assets") / "GameCreater"

    def create(self, request: EngineSyncProfileCreate) -> EngineSyncProfile:
        name = request.name.strip()
        if not name:
            raise ValueError("Profile name cannot be empty")
        root = self._validate_project_root(request.engine, request.project_root)
        asset_ids = self._validate_assets(request.asset_ids)
        profile_id = f"sync_{uuid4().hex[:12]}"
        now = utc_now()
        with self._connect() as db:
            db.execute(
                "INSERT INTO engine_sync_profiles(id,name,engine,project_root,asset_ids_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                (profile_id, name, request.engine.value, str(root), json.dumps(asset_ids), now, now),
            )
        return self.get(profile_id)

    def list(self) -> list[EngineSyncProfile]:
        with self._connect() as db:
            ids = [row["id"] for row in db.execute("SELECT id FROM engine_sync_profiles ORDER BY updated_at DESC,id").fetchall()]
        return [self.get(profile_id) for profile_id in ids]

    def get(self, profile_id: str) -> EngineSyncProfile:
        with self._connect() as db:
            row = db.execute("SELECT * FROM engine_sync_profiles WHERE id=?", (profile_id,)).fetchone()
        if row is None:
            raise EngineSyncProfileNotFoundError(profile_id)
        engine = EngineSyncEngine(row["engine"])
        return EngineSyncProfile(
            id=row["id"],
            name=row["name"],
            engine=engine,
            project_root=row["project_root"],
            managed_root=self._managed_relative(engine).as_posix(),
            asset_ids=json.loads(row["asset_ids_json"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def patch(self, profile_id: str, patch: EngineSyncProfilePatch) -> EngineSyncProfile:
        current = self.get(profile_id)
        name = current.name if patch.name is None else patch.name.strip()
        if not name:
            raise ValueError("Profile name cannot be empty")
        root = Path(current.project_root)
        if patch.project_root is not None:
            root = self._validate_project_root(current.engine, patch.project_root)
        else:
            self._validate_project_root(current.engine, current.project_root)
        asset_ids = current.asset_ids if patch.asset_ids is None else self._validate_assets(patch.asset_ids)
        with self._connect() as db:
            db.execute(
                "UPDATE engine_sync_profiles SET name=?,project_root=?,asset_ids_json=?,updated_at=? WHERE id=?",
                (name, str(root), json.dumps(asset_ids), utc_now(), profile_id),
            )
        return self.get(profile_id)

    @staticmethod
    def _sha_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def _sha_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _desired_files(self, profile: EngineSyncProfile) -> dict[str, tuple[Path | None, bytes | None]]:
        desired: dict[str, tuple[Path | None, bytes | None]] = {}
        manifest_assets: list[dict] = []
        for asset_id in profile.asset_ids:
            asset = self.library.get(asset_id)
            versions = {version.version: version for version in self.library.list_versions(asset_id)}
            active = versions.get(asset.active_version)
            if active is None:
                raise ValueError(f"Active version is missing: {asset_id} v{asset.active_version}")
            runtime = self.runtime.get(asset_id)
            file_entries: dict[str, str] = {}
            for folder, rel, filename in (
                ("assets", active.image_path, f"{asset_id}.png"),
                ("masks", active.mask_path, f"{asset_id}.png"),
                ("alpha", active.alpha_path, f"{asset_id}.png"),
            ):
                if not rel:
                    continue
                source = (self.workspace / rel).resolve()
                if not source.is_file():
                    raise FileNotFoundError(source)
                relative = (Path(folder) / filename).as_posix()
                desired[relative] = (source, None)
                file_entries[folder] = relative

            metadata = {
                "schema": "game-creater/engine-asset/v1",
                "asset_id": asset.id,
                "name": asset.name,
                "category": asset.category,
                "subcategory": asset.subcategory,
                "tags": asset.tags,
                "active_version": asset.active_version,
                "files": file_entries,
                "runtime": runtime.model_dump(mode="json"),
            }
            metadata_bytes = json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
            metadata_rel = (Path("metadata") / f"{asset_id}.json").as_posix()
            desired[metadata_rel] = (None, metadata_bytes)
            manifest_assets.append(
                {
                    "asset_id": asset.id,
                    "version": asset.active_version,
                    "metadata": metadata_rel,
                    "files": file_entries,
                }
            )

        manifest = {
            "schema": "game-creater/engine-sync/v1",
            "profile_id": profile.id,
            "engine": profile.engine.value,
            "assets": manifest_assets,
        }
        desired[self.MANIFEST_NAME] = (
            None,
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"),
        )
        return desired

    def _managed_root(self, profile: EngineSyncProfile, *, create: bool = False) -> Path:
        project_root = self._validate_project_root(profile.engine, profile.project_root)
        managed = (project_root / self._managed_relative(profile.engine)).resolve()
        if not managed.is_relative_to(project_root):
            raise ValueError("Managed sync root escapes the project root")
        if create:
            managed.mkdir(parents=True, exist_ok=True)
        return managed

    def _plan_with_desired(self, profile: EngineSyncProfile, desired: dict[str, tuple[Path | None, bytes | None]]) -> EngineSyncPlan:
        managed = self._managed_root(profile)
        files: list[EngineSyncFile] = []
        expected = set(desired)
        add_count = update_count = unchanged_count = 0
        for relative, (source_path, content) in sorted(desired.items()):
            source_hash = self._sha_file(source_path) if source_path is not None else self._sha_bytes(content or b"")
            target = managed / Path(relative)
            target_hash = self._sha_file(target) if target.is_file() else None
            if target_hash is None:
                action = "add"
                add_count += 1
            elif target_hash != source_hash:
                action = "update"
                update_count += 1
            else:
                action = "unchanged"
                unchanged_count += 1
            files.append(
                EngineSyncFile(
                    relative_path=relative,
                    source_path=str(source_path) if source_path is not None else None,
                    source_sha256=source_hash,
                    target_sha256=target_hash,
                    action=action,
                )
            )

        stale: list[str] = []
        if managed.is_dir():
            for path in sorted(managed.rglob("*")):
                if not path.is_file():
                    continue
                relative = path.relative_to(managed).as_posix()
                if relative not in expected:
                    stale.append(relative)
                    files.append(
                        EngineSyncFile(
                            relative_path=relative,
                            target_sha256=self._sha_file(path),
                            action="stale",
                        )
                    )
        return EngineSyncPlan(
            profile_id=profile.id,
            engine=profile.engine,
            managed_root=str(managed),
            files=files,
            stale_paths=stale,
            add_count=add_count,
            update_count=update_count,
            unchanged_count=unchanged_count,
        )

    def plan(self, profile_id: str) -> EngineSyncPlan:
        profile = self.get(profile_id)
        desired = self._desired_files(profile)
        return self._plan_with_desired(profile, desired)

    def sync(self, profile_id: str) -> EngineSyncResult:
        profile = self.get(profile_id)
        desired = self._desired_files(profile)
        plan = self._plan_with_desired(profile, desired)
        managed = self._managed_root(profile, create=True)
        copied: list[str] = []
        unchanged: list[str] = []
        actions = {item.relative_path: item.action for item in plan.files}
        for relative, (source_path, content) in desired.items():
            action = actions[relative]
            target = (managed / Path(relative)).resolve()
            if not target.is_relative_to(managed):
                raise ValueError("Sync target escapes managed root")
            if action == "unchanged":
                unchanged.append(relative)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if source_path is not None:
                target.write_bytes(source_path.read_bytes())
            else:
                target.write_bytes(content or b"")
            copied.append(relative)
        synced_at = utc_now()
        with self._connect() as db:
            db.execute(
                "INSERT INTO engine_sync_history(profile_id,copied_count,unchanged_count,synced_at) VALUES (?,?,?,?)",
                (profile_id, len(copied), len(unchanged), synced_at),
            )
        return EngineSyncResult(
            profile_id=profile_id,
            copied=copied,
            unchanged=unchanged,
            manifest_path=str(managed / self.MANIFEST_NAME),
            synced_at=synced_at,
        )

    def prune(self, profile_id: str, relative_paths: list[str]) -> EngineSyncPruneResult:
        profile = self.get(profile_id)
        plan = self.plan(profile_id)
        allowed = set(plan.stale_paths)
        requested = list(dict.fromkeys(item.strip().replace("\\", "/") for item in relative_paths if item.strip()))
        if not requested:
            raise ValueError("At least one stale path is required")
        if not set(requested).issubset(allowed):
            raise ValueError("Prune may remove only paths currently reported as stale")
        managed = self._managed_root(profile)
        removed: list[str] = []
        for relative in requested:
            target = (managed / Path(relative)).resolve()
            if not target.is_relative_to(managed):
                raise ValueError("Prune target escapes managed root")
            if target.is_file():
                target.unlink()
                removed.append(relative)
        for directory in sorted((path for path in managed.rglob("*") if path.is_dir()), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass
        return EngineSyncPruneResult(profile_id=profile_id, removed=removed)
