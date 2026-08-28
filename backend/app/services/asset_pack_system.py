from __future__ import annotations

import json
import re
import shutil
import zipfile
from pathlib import Path
from uuid import uuid4

from app.asset_pack_models import (
    AssetPackAssetLock,
    AssetPackCreateRequest,
    AssetPackDefinition,
    AssetPackDependency,
    AssetPackExportResult,
    AssetPackInstallation,
    AssetPackRelease,
    AssetPackReleaseRequest,
    AssetPackUpdateInfo,
    AssetPackUpdateRequest,
)
from app.services.asset_library import AssetLibrary, LibraryAssetNotFoundError, utc_now


class AssetPackNotFoundError(KeyError):
    pass


class AssetPackReleaseNotFoundError(KeyError):
    pass


class AssetPackSystemService:
    VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace)
        self.library = AssetLibrary(self.workspace)
        self.state_root = self.workspace.parent / ".game_creater_state" / "pack_exports"
        self.state_root.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        with self.library._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS game_asset_packs (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    asset_ids_json TEXT NOT NULL,
                    dependencies_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS game_asset_pack_releases (
                    pack_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT '',
                    manifest_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(pack_id, version),
                    FOREIGN KEY(pack_id) REFERENCES game_asset_packs(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS game_asset_pack_installations (
                    pack_id TEXT PRIMARY KEY,
                    version TEXT NOT NULL,
                    lock_json TEXT NOT NULL,
                    installed_at TEXT NOT NULL,
                    FOREIGN KEY(pack_id) REFERENCES game_asset_packs(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_asset_pack_release_pack ON game_asset_pack_releases(pack_id);
                """
            )

    @classmethod
    def _version_tuple(cls, version: str) -> tuple[int, int, int]:
        match = cls.VERSION_RE.fullmatch(version.strip())
        if not match:
            raise ValueError("Version must use semantic version format MAJOR.MINOR.PATCH")
        return tuple(int(part) for part in match.groups())

    def _validate_assets(self, asset_ids: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(item.strip() for item in asset_ids if item.strip()))
        if not normalized:
            raise ValueError("Pack must contain at least one asset")
        for asset_id in normalized:
            self.library.get(asset_id)
        return normalized

    @staticmethod
    def _dependencies_json(dependencies: list[AssetPackDependency]) -> str:
        seen: set[str] = set()
        items = []
        for dependency in dependencies:
            pack_id = dependency.pack_id.strip()
            if not pack_id or pack_id in seen:
                continue
            seen.add(pack_id)
            items.append({"pack_id": pack_id, "version": dependency.version})
        return json.dumps(items, ensure_ascii=False)

    def create(self, request: AssetPackCreateRequest) -> AssetPackDefinition:
        name = request.name.strip()
        if not name:
            raise ValueError("Pack name cannot be empty")
        asset_ids = self._validate_assets(request.asset_ids)
        pack_id = f"pack_{uuid4().hex[:12]}"
        self._validate_dependencies(pack_id, request.dependencies, allow_missing=False)
        now = utc_now()
        with self.library._connect() as db:
            db.execute(
                "INSERT INTO game_asset_packs(id,name,description,asset_ids_json,dependencies_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                (pack_id, name, request.description.strip(), json.dumps(asset_ids), self._dependencies_json(request.dependencies), now, now),
            )
        return self.get(pack_id)

    def list(self) -> list[AssetPackDefinition]:
        with self.library._connect() as db:
            ids = [row["id"] for row in db.execute("SELECT id FROM game_asset_packs ORDER BY updated_at DESC,id").fetchall()]
        return [self.get(pack_id) for pack_id in ids]

    def get(self, pack_id: str) -> AssetPackDefinition:
        with self.library._connect() as db:
            row = db.execute("SELECT * FROM game_asset_packs WHERE id=?", (pack_id,)).fetchone()
            if row is None:
                raise AssetPackNotFoundError(pack_id)
            release_rows = db.execute("SELECT version FROM game_asset_pack_releases WHERE pack_id=?", (pack_id,)).fetchall()
        versions = [item["version"] for item in release_rows]
        latest = max(versions, key=self._version_tuple) if versions else None
        return AssetPackDefinition(
            id=row["id"], name=row["name"], description=row["description"],
            asset_ids=json.loads(row["asset_ids_json"]),
            dependencies=[AssetPackDependency(**item) for item in json.loads(row["dependencies_json"] or "[]")],
            latest_version=latest, created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def update(self, pack_id: str, request: AssetPackUpdateRequest) -> AssetPackDefinition:
        current = self.get(pack_id)
        name = current.name if request.name is None else request.name.strip()
        if not name:
            raise ValueError("Pack name cannot be empty")
        description = current.description if request.description is None else request.description.strip()
        asset_ids = current.asset_ids if request.asset_ids is None else self._validate_assets(request.asset_ids)
        dependencies = current.dependencies if request.dependencies is None else request.dependencies
        self._validate_dependencies(pack_id, dependencies, allow_missing=False)
        now = utc_now()
        with self.library._connect() as db:
            db.execute(
                "UPDATE game_asset_packs SET name=?,description=?,asset_ids_json=?,dependencies_json=?,updated_at=? WHERE id=?",
                (name, description, json.dumps(asset_ids), self._dependencies_json(dependencies), now, pack_id),
            )
        self._assert_no_cycle(pack_id)
        return self.get(pack_id)

    def _validate_dependencies(self, pack_id: str, dependencies: list[AssetPackDependency], *, allow_missing: bool) -> None:
        for dependency in dependencies:
            if dependency.pack_id == pack_id:
                raise ValueError("Pack cannot depend on itself")
            if dependency.version is not None:
                self._version_tuple(dependency.version)
            try:
                self.get(dependency.pack_id)
            except AssetPackNotFoundError:
                if not allow_missing:
                    raise ValueError(f"Dependency pack not found: {dependency.pack_id}")

    def _assert_no_cycle(self, start_pack_id: str) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(pack_id: str) -> None:
            if pack_id in visiting:
                raise ValueError("Asset Pack dependency cycle detected")
            if pack_id in visited:
                return
            visiting.add(pack_id)
            for dependency in self.get(pack_id).dependencies:
                visit(dependency.pack_id)
            visiting.remove(pack_id)
            visited.add(pack_id)

        visit(start_pack_id)

    def release(self, pack_id: str, request: AssetPackReleaseRequest) -> AssetPackRelease:
        pack = self.get(pack_id)
        version = request.version.strip()
        self._version_tuple(version)
        dependencies = []
        for dependency in pack.dependencies:
            resolved = dependency.version or self._latest_version(dependency.pack_id)
            if resolved is None:
                raise ValueError(f"Dependency has no release: {dependency.pack_id}")
            self.get_release(dependency.pack_id, resolved)
            dependencies.append(AssetPackDependency(pack_id=dependency.pack_id, version=resolved))

        locks: list[AssetPackAssetLock] = []
        for asset_id in pack.asset_ids:
            asset = self.library.get(asset_id)
            versions = {item.version: item for item in self.library.list_versions(asset_id)}
            active = versions.get(asset.active_version)
            if active is None:
                raise ValueError(f"Active asset version missing: {asset_id} v{asset.active_version}")
            locks.append(AssetPackAssetLock(
                asset_id=asset.id,
                version=asset.active_version,
                name=asset.name,
                image_path=active.image_path,
                mask_path=active.mask_path,
                alpha_path=active.alpha_path,
            ))
        now = utc_now()
        release = AssetPackRelease(pack_id=pack_id, version=version, notes=request.notes.strip(), assets=locks, dependencies=dependencies, created_at=now)
        try:
            with self.library._connect() as db:
                db.execute(
                    "INSERT INTO game_asset_pack_releases(pack_id,version,notes,manifest_json,created_at) VALUES (?,?,?,?,?)",
                    (pack_id, version, release.notes, release.model_dump_json(), now),
                )
        except Exception as exc:
            if "UNIQUE" in str(exc).upper():
                raise ValueError(f"Release already exists: {pack_id} {version}") from exc
            raise
        return release

    def list_releases(self, pack_id: str) -> list[AssetPackRelease]:
        self.get(pack_id)
        with self.library._connect() as db:
            rows = db.execute("SELECT manifest_json FROM game_asset_pack_releases WHERE pack_id=?", (pack_id,)).fetchall()
        releases = [AssetPackRelease.model_validate_json(row["manifest_json"]) for row in rows]
        releases.sort(key=lambda item: self._version_tuple(item.version), reverse=True)
        return releases

    def get_release(self, pack_id: str, version: str) -> AssetPackRelease:
        self._version_tuple(version)
        with self.library._connect() as db:
            row = db.execute("SELECT manifest_json FROM game_asset_pack_releases WHERE pack_id=? AND version=?", (pack_id, version)).fetchone()
        if row is None:
            raise AssetPackReleaseNotFoundError(f"{pack_id}@{version}")
        return AssetPackRelease.model_validate_json(row["manifest_json"])

    def _latest_version(self, pack_id: str) -> str | None:
        releases = self.list_releases(pack_id)
        return releases[0].version if releases else None

    def install(self, pack_id: str, version: str | None = None) -> AssetPackInstallation:
        root_version = version or self._latest_version(pack_id)
        if root_version is None:
            raise ValueError("Pack has no release to install")
        resolved: dict[str, str] = {}
        asset_locks: dict[str, dict] = {}
        visiting: set[str] = set()

        def resolve(current_pack: str, current_version: str) -> None:
            if current_pack in visiting:
                raise ValueError("Asset Pack dependency cycle detected during install")
            if current_pack in resolved:
                if resolved[current_pack] != current_version:
                    raise ValueError(f"Dependency version conflict for {current_pack}: {resolved[current_pack]} vs {current_version}")
                return
            visiting.add(current_pack)
            release = self.get_release(current_pack, current_version)
            for dependency in release.dependencies:
                if dependency.version is None:
                    raise ValueError("Released dependency must be version-pinned")
                resolve(dependency.pack_id, dependency.version)
            for asset in release.assets:
                key = asset.asset_id
                existing = asset_locks.get(key)
                if existing and existing["version"] != asset.version:
                    raise ValueError(f"Asset version conflict for {key}")
                asset_locks[key] = asset.model_dump()
            visiting.remove(current_pack)
            resolved[current_pack] = current_version

        resolve(pack_id, root_version)
        now = utc_now()
        lock = {
            "schema": "game-creater/asset-pack-lock/v1",
            "root": {"pack_id": pack_id, "version": root_version},
            "packs": resolved,
            "assets": asset_locks,
        }
        with self.library._connect() as db:
            for dependency_pack_id, dependency_version in resolved.items():
                db.execute(
                    "INSERT INTO game_asset_pack_installations(pack_id,version,lock_json,installed_at) VALUES (?,?,?,?) ON CONFLICT(pack_id) DO UPDATE SET version=excluded.version,lock_json=excluded.lock_json,installed_at=excluded.installed_at",
                    (dependency_pack_id, dependency_version, json.dumps(lock, ensure_ascii=False), now),
                )
        return self.get_installation(pack_id)

    def list_installations(self) -> list[AssetPackInstallation]:
        with self.library._connect() as db:
            rows = db.execute("SELECT * FROM game_asset_pack_installations ORDER BY installed_at DESC,pack_id").fetchall()
        return [AssetPackInstallation(pack_id=row["pack_id"], version=row["version"], installed_at=row["installed_at"], lock=json.loads(row["lock_json"])) for row in rows]

    def get_installation(self, pack_id: str) -> AssetPackInstallation:
        with self.library._connect() as db:
            row = db.execute("SELECT * FROM game_asset_pack_installations WHERE pack_id=?", (pack_id,)).fetchone()
        if row is None:
            raise AssetPackNotFoundError(f"Pack is not installed: {pack_id}")
        return AssetPackInstallation(pack_id=row["pack_id"], version=row["version"], installed_at=row["installed_at"], lock=json.loads(row["lock_json"]))

    def uninstall(self, pack_id: str) -> None:
        with self.library._connect() as db:
            db.execute("DELETE FROM game_asset_pack_installations WHERE pack_id=?", (pack_id,))

    def updates(self) -> list[AssetPackUpdateInfo]:
        result = []
        for installed in self.list_installations():
            latest = self._latest_version(installed.pack_id) or installed.version
            result.append(AssetPackUpdateInfo(
                pack_id=installed.pack_id,
                installed_version=installed.version,
                latest_version=latest,
                update_available=self._version_tuple(latest) > self._version_tuple(installed.version),
            ))
        return result

    def export_release(self, pack_id: str, version: str | None = None) -> AssetPackExportResult:
        resolved_version = version or self._latest_version(pack_id)
        if resolved_version is None:
            raise ValueError("Pack has no release to export")
        release = self.get_release(pack_id, resolved_version)
        export_id = f"pkgexp_{uuid4().hex[:12]}"
        root = self.state_root / export_id
        if root.exists():
            shutil.rmtree(root)
        (root / "assets").mkdir(parents=True)
        pack = self.get(pack_id)
        manifest = {
            "schema": "game-creater/asset-pack/v1",
            "pack": pack.model_dump(mode="json"),
            "release": release.model_dump(mode="json"),
        }
        (root / "pack.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        for locked in release.assets:
            asset_dir = root / "assets" / locked.asset_id
            asset_dir.mkdir(parents=True)
            for label, rel in (("asset.png", locked.image_path), ("mask.png", locked.mask_path), ("alpha.png", locked.alpha_path)):
                if not rel:
                    continue
                src = self.workspace / rel
                if src.is_file():
                    shutil.copy2(src, asset_dir / label)
            (asset_dir / "asset.json").write_text(json.dumps(locked.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        archive = self.state_root / f"{export_id}.zip"
        archive.unlink(missing_ok=True)
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as out:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    out.write(path, path.relative_to(root))
        return AssetPackExportResult(export_id=export_id, pack_id=pack_id, version=resolved_version, archive_path=str(archive), download_url=f"/api/v1/library/package-system/exports/{export_id}")

    def export_path(self, export_id: str) -> Path:
        if not re.fullmatch(r"pkgexp_[0-9a-f]{12}", export_id):
            raise ValueError("Invalid pack export id")
        path = self.state_root / f"{export_id}.zip"
        if not path.is_file():
            raise FileNotFoundError(path)
        return path
