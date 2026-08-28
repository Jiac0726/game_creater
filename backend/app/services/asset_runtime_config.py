from __future__ import annotations

import json
from pathlib import Path

from app.asset_runtime_models import (
    AssetRuntimeConfig,
    AssetRuntimeConfigPatch,
    BulkAssetRuntimeConfigPatch,
    CollisionMode,
)
from app.services.asset_library import AssetLibrary, LibraryAssetNotFoundError, utc_now


class AssetRuntimeConfigService:
    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace)
        self.library = AssetLibrary(self.workspace)
        self._init_schema()

    def _init_schema(self) -> None:
        with self.library._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS asset_runtime_config (
                    asset_id TEXT PRIMARY KEY,
                    pivot_x REAL NOT NULL DEFAULT 0.5,
                    pivot_y REAL NOT NULL DEFAULT 1.0,
                    pixels_per_unit REAL NOT NULL DEFAULT 100.0,
                    render_layer TEXT NOT NULL DEFAULT 'default',
                    sorting_order INTEGER NOT NULL DEFAULT 0,
                    collision_mode TEXT NOT NULL DEFAULT 'none',
                    collision_is_trigger INTEGER NOT NULL DEFAULT 0,
                    gameplay_tags_json TEXT NOT NULL DEFAULT '[]',
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE CASCADE
                )
                """
            )

    def get(self, asset_id: str) -> AssetRuntimeConfig:
        self.library.get(asset_id)
        with self.library._connect() as db:
            row = db.execute(
                "SELECT * FROM asset_runtime_config WHERE asset_id=?",
                (asset_id,),
            ).fetchone()
            if row is None:
                now = utc_now()
                db.execute(
                    "INSERT INTO asset_runtime_config(asset_id,updated_at) VALUES (?,?)",
                    (asset_id, now),
                )
                row = db.execute(
                    "SELECT * FROM asset_runtime_config WHERE asset_id=?",
                    (asset_id,),
                ).fetchone()
        return self._hydrate(row)

    def patch(self, asset_id: str, patch: AssetRuntimeConfigPatch) -> AssetRuntimeConfig:
        self.library.get(asset_id)
        current = self.get(asset_id)
        updates = patch.model_dump(exclude_unset=True)
        if "collision_mode" in updates and hasattr(updates["collision_mode"], "value"):
            updates["collision_mode"] = updates["collision_mode"].value
        if "render_layer" in updates:
            updates["render_layer"] = (updates["render_layer"] or "default").strip() or "default"
        if "gameplay_tags" in updates:
            tags: list[str] = []
            seen: set[str] = set()
            for raw in updates.pop("gameplay_tags") or []:
                value = raw.strip()
                key = value.lower()
                if value and key not in seen:
                    seen.add(key)
                    tags.append(value)
            updates["gameplay_tags_json"] = json.dumps(tags, ensure_ascii=False)
        if "collision_is_trigger" in updates:
            updates["collision_is_trigger"] = int(bool(updates["collision_is_trigger"]))
        if not updates:
            return current
        updates["updated_at"] = utc_now()
        with self.library._connect() as db:
            assignments = ", ".join(f"{key}=?" for key in updates)
            db.execute(
                f"UPDATE asset_runtime_config SET {assignments} WHERE asset_id=?",
                [*updates.values(), asset_id],
            )
        return self.get(asset_id)

    def bulk_patch(self, request: BulkAssetRuntimeConfigPatch) -> list[AssetRuntimeConfig]:
        results: list[AssetRuntimeConfig] = []
        seen: set[str] = set()
        for asset_id in request.asset_ids:
            if asset_id in seen:
                continue
            seen.add(asset_id)
            results.append(self.patch(asset_id, request.patch))
        return results

    def snapshot(self, asset_ids: list[str]) -> list[AssetRuntimeConfig]:
        return [self.get(asset_id) for asset_id in asset_ids]

    @staticmethod
    def _hydrate(row) -> AssetRuntimeConfig:
        return AssetRuntimeConfig(
            asset_id=row["asset_id"],
            pivot_x=float(row["pivot_x"]),
            pivot_y=float(row["pivot_y"]),
            pixels_per_unit=float(row["pixels_per_unit"]),
            render_layer=row["render_layer"],
            sorting_order=int(row["sorting_order"]),
            collision_mode=CollisionMode(row["collision_mode"]),
            collision_is_trigger=bool(row["collision_is_trigger"]),
            gameplay_tags=json.loads(row["gameplay_tags_json"] or "[]"),
            updated_at=row["updated_at"],
        )
