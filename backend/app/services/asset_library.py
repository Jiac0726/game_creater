from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from PIL import Image

from app.asset_library_models import (
    AssetLibraryStats,
    AssetRelationType,
    AssetReviewState,
    AssetSearchResult,
    LibraryAsset,
    LibraryAssetPatch,
    LibraryAssetVersion,
)
from app.models import AssetRecord, SceneManifest


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AssetLibraryError(RuntimeError):
    pass


class LibraryAssetNotFoundError(KeyError):
    pass


class CollectionNotFoundError(KeyError):
    pass


class AssetLibrary:
    """SQLite metadata/index layer for reusable game assets.

    The library never duplicates source image files. It indexes paths under the
    existing workspace and tracks metadata, versions, tags, collections,
    relations and provenance by stable global asset IDs.
    """

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.db_path = self.workspace / "asset_library.db"
        self._init_schema()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _init_schema(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS assets (
                    id TEXT PRIMARY KEY,
                    scene_id TEXT NOT NULL,
                    scene_asset_id TEXT NOT NULL,
                    project_id TEXT,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'uncategorized',
                    subcategory TEXT NOT NULL DEFAULT '',
                    review_state TEXT NOT NULL DEFAULT 'needs_review',
                    favorite INTEGER NOT NULL DEFAULT 0,
                    confidence REAL NOT NULL DEFAULT 0,
                    asset_score REAL NOT NULL DEFAULT 0,
                    width INTEGER NOT NULL DEFAULT 0,
                    height INTEGER NOT NULL DEFAULT 0,
                    image_path TEXT NOT NULL,
                    mask_path TEXT NOT NULL,
                    alpha_path TEXT,
                    source_image_path TEXT,
                    completed INTEGER NOT NULL DEFAULT 0,
                    active_version INTEGER NOT NULL DEFAULT 1,
                    notes TEXT,
                    provenance_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(scene_id, scene_asset_id)
                );

                CREATE INDEX IF NOT EXISTS idx_assets_scene ON assets(scene_id);
                CREATE INDEX IF NOT EXISTS idx_assets_name ON assets(name);
                CREATE INDEX IF NOT EXISTS idx_assets_category ON assets(category);
                CREATE INDEX IF NOT EXISTS idx_assets_review_state ON assets(review_state);
                CREATE INDEX IF NOT EXISTS idx_assets_score ON assets(asset_score);

                CREATE TABLE IF NOT EXISTS asset_versions (
                    asset_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    image_path TEXT NOT NULL,
                    mask_path TEXT,
                    alpha_path TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(asset_id, version),
                    FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE COLLATE NOCASE
                );

                CREATE TABLE IF NOT EXISTS asset_tags (
                    asset_id TEXT NOT NULL,
                    tag_id INTEGER NOT NULL,
                    PRIMARY KEY(asset_id, tag_id),
                    FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE CASCADE,
                    FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS collections (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    description TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS collection_assets (
                    collection_id TEXT NOT NULL,
                    asset_id TEXT NOT NULL,
                    PRIMARY KEY(collection_id, asset_id),
                    FOREIGN KEY(collection_id) REFERENCES collections(id) ON DELETE CASCADE,
                    FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS asset_relations (
                    source_asset_id TEXT NOT NULL,
                    target_asset_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(source_asset_id, target_asset_id, relation_type),
                    FOREIGN KEY(source_asset_id) REFERENCES assets(id) ON DELETE CASCADE,
                    FOREIGN KEY(target_asset_id) REFERENCES assets(id) ON DELETE CASCADE
                );
                """
            )

    def sync_scene(self, manifest: SceneManifest, project_id: str | None = None) -> SceneManifest:
        """Upsert all current scene assets and archive scene assets removed later."""
        active_scene_asset_ids: set[str] = set()
        for asset in manifest.assets:
            active_scene_asset_ids.add(asset.id)
            self._upsert_scene_asset(manifest, asset, project_id=project_id)

        with self._connect() as db:
            rows = db.execute(
                "SELECT id, scene_asset_id FROM assets WHERE scene_id=?",
                (manifest.scene_id,),
            ).fetchall()
            now = utc_now()
            for row in rows:
                if row["scene_asset_id"] not in active_scene_asset_ids:
                    db.execute(
                        "UPDATE assets SET review_state=?, updated_at=? WHERE id=?",
                        (AssetReviewState.ARCHIVED.value, now, row["id"]),
                    )
        return manifest

    def _upsert_scene_asset(
        self,
        manifest: SceneManifest,
        asset: AssetRecord,
        *,
        project_id: str | None,
    ) -> str:
        now = utc_now()
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM assets WHERE scene_id=? AND scene_asset_id=?",
                (manifest.scene_id, asset.id),
            ).fetchone()

            global_id = getattr(asset, "library_asset_id", None) or (row["id"] if row else None)
            if not global_id:
                global_id = f"asset_{uuid4().hex[:16]}"
            if hasattr(asset, "library_asset_id"):
                asset.library_asset_id = global_id

            image_path = f"{manifest.scene_id}/{asset.image}"
            mask_path = f"{manifest.scene_id}/{asset.mask}"
            alpha_path = f"{manifest.scene_id}/{asset.alpha}" if asset.alpha else None
            source_image_path = (
                f"{manifest.scene_id}/{manifest.source_file}" if manifest.source_file else None
            )
            width = max(0, asset.bbox.x2 - asset.bbox.x1)
            height = max(0, asset.bbox.y2 - asset.bbox.y1)
            review_state = self._default_review_state(asset)
            provenance = {
                "scene_id": manifest.scene_id,
                "scene_asset_id": asset.id,
                "source_image": manifest.source_image,
                "source_file": manifest.source_file,
                "mode": manifest.mode,
                "prompts": manifest.prompts,
                "bbox": asset.bbox.model_dump(),
                "score_components": asset.score_components,
            }
            if project_id:
                provenance["project_id"] = project_id

            if row is None:
                db.execute(
                    """
                    INSERT INTO assets (
                        id, scene_id, scene_asset_id, project_id, name, category,
                        review_state, confidence, asset_score, width, height,
                        image_path, mask_path, alpha_path, source_image_path,
                        completed, active_version, notes, provenance_json,
                        created_at, updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        global_id,
                        manifest.scene_id,
                        asset.id,
                        project_id,
                        asset.label,
                        asset.category,
                        review_state,
                        asset.confidence,
                        asset.asset_score,
                        width,
                        height,
                        image_path,
                        mask_path,
                        alpha_path,
                        source_image_path,
                        int(asset.completed),
                        1,
                        asset.notes,
                        json.dumps(provenance, ensure_ascii=False),
                        now,
                        now,
                    ),
                )
                db.execute(
                    """
                    INSERT INTO asset_versions (
                        asset_id, version, kind, image_path, mask_path, alpha_path,
                        metadata_json, created_at
                    ) VALUES (?,?,?,?,?,?,?,?)
                    """,
                    (
                        global_id,
                        1,
                        "segmented",
                        image_path,
                        mask_path,
                        alpha_path,
                        json.dumps({"source": "scene_sync"}, ensure_ascii=False),
                        now,
                    ),
                )
            else:
                existing_state = row["review_state"]
                if existing_state in {
                    AssetReviewState.APPROVED.value,
                    AssetReviewState.PRODUCTION_READY.value,
                    AssetReviewState.IN_USE.value,
                }:
                    review_state = existing_state
                db.execute(
                    """
                    UPDATE assets SET
                        project_id=COALESCE(?, project_id), name=?, category=?,
                        review_state=?, confidence=?, asset_score=?, width=?, height=?,
                        image_path=?, mask_path=?, alpha_path=?, source_image_path=?,
                        completed=?, notes=?, provenance_json=?, updated_at=?
                    WHERE id=?
                    """,
                    (
                        project_id,
                        asset.label,
                        asset.category,
                        review_state,
                        asset.confidence,
                        asset.asset_score,
                        width,
                        height,
                        image_path,
                        mask_path,
                        alpha_path,
                        source_image_path,
                        int(asset.completed),
                        asset.notes,
                        json.dumps(provenance, ensure_ascii=False),
                        now,
                        global_id,
                    ),
                )
            return global_id

    @staticmethod
    def _default_review_state(asset: AssetRecord) -> str:
        if asset.asset_score >= 0.82 and asset.confidence >= 0.65:
            return AssetReviewState.NEEDS_REVIEW.value
        return AssetReviewState.NEEDS_REVIEW.value

    def add_version(
        self,
        asset_id: str,
        *,
        kind: str,
        image_path: str,
        mask_path: str | None = None,
        alpha_path: str | None = None,
        metadata: dict | None = None,
        activate: bool = True,
    ) -> LibraryAssetVersion:
        with self._connect() as db:
            row = db.execute("SELECT id FROM assets WHERE id=?", (asset_id,)).fetchone()
            if row is None:
                raise LibraryAssetNotFoundError(asset_id)
            version = int(
                db.execute(
                    "SELECT COALESCE(MAX(version), 0) + 1 AS next_version FROM asset_versions WHERE asset_id=?",
                    (asset_id,),
                ).fetchone()["next_version"]
            )
            now = utc_now()
            db.execute(
                """
                INSERT INTO asset_versions (
                    asset_id, version, kind, image_path, mask_path, alpha_path,
                    metadata_json, created_at
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    asset_id,
                    version,
                    kind,
                    image_path,
                    mask_path,
                    alpha_path,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    now,
                ),
            )
            if activate:
                db.execute(
                    """
                    UPDATE assets SET active_version=?, image_path=?,
                        mask_path=COALESCE(?, mask_path), alpha_path=COALESCE(?, alpha_path),
                        updated_at=? WHERE id=?
                    """,
                    (version, image_path, mask_path, alpha_path, now, asset_id),
                )
        return LibraryAssetVersion(
            version=version,
            kind=kind,
            image_path=image_path,
            mask_path=mask_path,
            alpha_path=alpha_path,
            created_at=now,
            metadata=metadata or {},
        )

    def list_versions(self, asset_id: str) -> list[LibraryAssetVersion]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM asset_versions WHERE asset_id=? ORDER BY version DESC",
                (asset_id,),
            ).fetchall()
        return [
            LibraryAssetVersion(
                version=row["version"],
                kind=row["kind"],
                image_path=row["image_path"],
                mask_path=row["mask_path"],
                alpha_path=row["alpha_path"],
                created_at=row["created_at"],
                metadata=json.loads(row["metadata_json"] or "{}"),
            )
            for row in rows
        ]

    def get(self, asset_id: str) -> LibraryAsset:
        with self._connect() as db:
            row = db.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
            if row is None:
                raise LibraryAssetNotFoundError(asset_id)
            return self._hydrate(db, row)

    def patch(self, asset_id: str, patch: LibraryAssetPatch) -> LibraryAsset:
        updates = patch.model_dump(exclude_unset=True)
        tags = updates.pop("tags", None)
        if "name" in updates:
            updates["name"] = (updates["name"] or "").strip()
            if not updates["name"]:
                raise ValueError("Asset name cannot be empty")
        if "category" in updates:
            updates["category"] = (updates["category"] or "uncategorized").strip() or "uncategorized"
        if "subcategory" in updates:
            updates["subcategory"] = (updates["subcategory"] or "").strip()
        if "review_state" in updates and hasattr(updates["review_state"], "value"):
            updates["review_state"] = updates["review_state"].value
        if "favorite" in updates:
            updates["favorite"] = int(bool(updates["favorite"]))

        allowed = {"name", "category", "subcategory", "review_state", "favorite", "notes"}
        updates = {key: value for key, value in updates.items() if key in allowed}
        with self._connect() as db:
            row = db.execute("SELECT id FROM assets WHERE id=?", (asset_id,)).fetchone()
            if row is None:
                raise LibraryAssetNotFoundError(asset_id)
            if updates:
                assignments = ", ".join(f"{key}=?" for key in updates)
                values = list(updates.values()) + [utc_now(), asset_id]
                db.execute(
                    f"UPDATE assets SET {assignments}, updated_at=? WHERE id=?",
                    values,
                )
            if tags is not None:
                self._replace_tags(db, asset_id, tags)
        return self.get(asset_id)

    def _replace_tags(self, db: sqlite3.Connection, asset_id: str, tags: Iterable[str]) -> None:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in tags:
            value = raw.strip()
            key = value.lower()
            if value and key not in seen:
                seen.add(key)
                normalized.append(value)
        db.execute("DELETE FROM asset_tags WHERE asset_id=?", (asset_id,))
        for tag in normalized:
            db.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (tag,))
            tag_id = db.execute("SELECT id FROM tags WHERE name=? COLLATE NOCASE", (tag,)).fetchone()["id"]
            db.execute(
                "INSERT OR IGNORE INTO asset_tags(asset_id, tag_id) VALUES (?,?)",
                (asset_id, tag_id),
            )

    def search(
        self,
        *,
        query: str = "",
        category: str | None = None,
        review_state: str | None = None,
        collection_id: str | None = None,
        favorite: bool | None = None,
        completed: bool | None = None,
        min_score: float | None = None,
        tags: list[str] | None = None,
        limit: int = 60,
        offset: int = 0,
    ) -> AssetSearchResult:
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        clauses = ["1=1"]
        params: list[object] = []
        joins: list[str] = []

        if query.strip():
            token = f"%{query.strip()}%"
            clauses.append("(a.name LIKE ? OR a.category LIKE ? OR a.subcategory LIKE ? OR a.notes LIKE ?)")
            params.extend([token, token, token, token])
        if category:
            clauses.append("a.category=?")
            params.append(category)
        if review_state:
            clauses.append("a.review_state=?")
            params.append(review_state)
        if favorite is not None:
            clauses.append("a.favorite=?")
            params.append(int(favorite))
        if completed is not None:
            clauses.append("a.completed=?")
            params.append(int(completed))
        if min_score is not None:
            clauses.append("a.asset_score>=?")
            params.append(float(min_score))
        if collection_id:
            joins.append("JOIN collection_assets ca ON ca.asset_id=a.id")
            clauses.append("ca.collection_id=?")
            params.append(collection_id)
        for index, tag in enumerate(tags or []):
            alias_at = f"at{index}"
            alias_t = f"t{index}"
            joins.append(f"JOIN asset_tags {alias_at} ON {alias_at}.asset_id=a.id")
            joins.append(f"JOIN tags {alias_t} ON {alias_t}.id={alias_at}.tag_id")
            clauses.append(f"{alias_t}.name=? COLLATE NOCASE")
            params.append(tag)

        from_sql = "assets a " + " ".join(joins)
        where_sql = " AND ".join(clauses)
        with self._connect() as db:
            total = db.execute(
                f"SELECT COUNT(DISTINCT a.id) AS total FROM {from_sql} WHERE {where_sql}",
                params,
            ).fetchone()["total"]
            rows = db.execute(
                f"""
                SELECT DISTINCT a.* FROM {from_sql}
                WHERE {where_sql}
                ORDER BY a.favorite DESC, a.asset_score DESC, a.updated_at DESC
                LIMIT ? OFFSET ?
                """,
                params + [limit, offset],
            ).fetchall()
            items = [self._hydrate(db, row) for row in rows]
        return AssetSearchResult(items=items, total=total, limit=limit, offset=offset)

    def create_collection(self, name: str, description: str = "") -> dict:
        clean = name.strip()
        if not clean:
            raise ValueError("Collection name cannot be empty")
        collection_id = f"col_{uuid4().hex[:12]}"
        now = utc_now()
        try:
            with self._connect() as db:
                db.execute(
                    "INSERT INTO collections(id,name,description,created_at,updated_at) VALUES (?,?,?,?,?)",
                    (collection_id, clean, description.strip(), now, now),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Collection name already exists") from exc
        return {"id": collection_id, "name": clean, "description": description.strip(), "created_at": now}

    def list_collections(self) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT c.*, COUNT(ca.asset_id) AS asset_count
                FROM collections c
                LEFT JOIN collection_assets ca ON ca.collection_id=c.id
                GROUP BY c.id
                ORDER BY c.name COLLATE NOCASE
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def add_to_collection(self, collection_id: str, asset_ids: Iterable[str]) -> None:
        with self._connect() as db:
            if db.execute("SELECT id FROM collections WHERE id=?", (collection_id,)).fetchone() is None:
                raise CollectionNotFoundError(collection_id)
            for asset_id in asset_ids:
                if db.execute("SELECT id FROM assets WHERE id=?", (asset_id,)).fetchone() is None:
                    raise LibraryAssetNotFoundError(asset_id)
                db.execute(
                    "INSERT OR IGNORE INTO collection_assets(collection_id,asset_id) VALUES (?,?)",
                    (collection_id, asset_id),
                )

    def remove_from_collection(self, collection_id: str, asset_id: str) -> None:
        with self._connect() as db:
            db.execute(
                "DELETE FROM collection_assets WHERE collection_id=? AND asset_id=?",
                (collection_id, asset_id),
            )

    def add_relation(
        self,
        source_asset_id: str,
        target_asset_id: str,
        relation_type: AssetRelationType | str,
    ) -> None:
        relation = relation_type.value if hasattr(relation_type, "value") else str(relation_type)
        if source_asset_id == target_asset_id:
            raise ValueError("An asset cannot relate to itself")
        with self._connect() as db:
            for asset_id in (source_asset_id, target_asset_id):
                if db.execute("SELECT id FROM assets WHERE id=?", (asset_id,)).fetchone() is None:
                    raise LibraryAssetNotFoundError(asset_id)
            db.execute(
                """
                INSERT OR IGNORE INTO asset_relations(
                    source_asset_id,target_asset_id,relation_type,created_at
                ) VALUES (?,?,?,?)
                """,
                (source_asset_id, target_asset_id, relation, utc_now()),
            )

    def relations(self, asset_id: str) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT source_asset_id,target_asset_id,relation_type,created_at
                FROM asset_relations
                WHERE source_asset_id=? OR target_asset_id=?
                ORDER BY created_at DESC
                """,
                (asset_id, asset_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def stats(self) -> AssetLibraryStats:
        with self._connect() as db:
            total = db.execute("SELECT COUNT(*) AS n FROM assets WHERE review_state!='archived'").fetchone()["n"]
            state_rows = db.execute(
                "SELECT review_state, COUNT(*) AS n FROM assets GROUP BY review_state"
            ).fetchall()
            categories = {
                row["category"]: row["n"]
                for row in db.execute(
                    "SELECT category, COUNT(*) AS n FROM assets WHERE review_state!='archived' GROUP BY category ORDER BY n DESC"
                ).fetchall()
            }
            counts = {row["review_state"]: row["n"] for row in state_rows}
            completed = db.execute("SELECT COUNT(*) AS n FROM assets WHERE completed=1").fetchone()["n"]
            favorites = db.execute("SELECT COUNT(*) AS n FROM assets WHERE favorite=1").fetchone()["n"]
            collections = db.execute("SELECT COUNT(*) AS n FROM collections").fetchone()["n"]
        return AssetLibraryStats(
            total_assets=total,
            needs_review=counts.get(AssetReviewState.NEEDS_REVIEW.value, 0),
            approved=counts.get(AssetReviewState.APPROVED.value, 0),
            production_ready=counts.get(AssetReviewState.PRODUCTION_READY.value, 0),
            completed_by_ai=completed,
            favorites=favorites,
            collections=collections,
            categories=categories,
        )

    def _hydrate(self, db: sqlite3.Connection, row: sqlite3.Row) -> LibraryAsset:
        tags = [
            item["name"]
            for item in db.execute(
                """
                SELECT t.name FROM tags t
                JOIN asset_tags at ON at.tag_id=t.id
                WHERE at.asset_id=? ORDER BY t.name COLLATE NOCASE
                """,
                (row["id"],),
            ).fetchall()
        ]
        collections = [
            item["id"]
            for item in db.execute(
                """
                SELECT c.id FROM collections c
                JOIN collection_assets ca ON ca.collection_id=c.id
                WHERE ca.asset_id=? ORDER BY c.name COLLATE NOCASE
                """,
                (row["id"],),
            ).fetchall()
        ]
        return LibraryAsset(
            id=row["id"],
            scene_id=row["scene_id"],
            scene_asset_id=row["scene_asset_id"],
            project_id=row["project_id"],
            name=row["name"],
            category=row["category"],
            subcategory=row["subcategory"],
            review_state=AssetReviewState(row["review_state"]),
            favorite=bool(row["favorite"]),
            confidence=row["confidence"],
            asset_score=row["asset_score"],
            width=row["width"],
            height=row["height"],
            image_path=row["image_path"],
            mask_path=row["mask_path"],
            alpha_path=row["alpha_path"],
            source_image_path=row["source_image_path"],
            completed=bool(row["completed"]),
            active_version=row["active_version"],
            notes=row["notes"],
            tags=tags,
            collections=collections,
            provenance=json.loads(row["provenance_json"] or "{}"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
