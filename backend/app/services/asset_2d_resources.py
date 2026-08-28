from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import numpy as np
from PIL import Image

from app.asset_2d_models import (
    AnimationClip,
    AnimationClipCreateRequest,
    AnimationClipPatch,
    CollisionPoint,
    CollisionPolygon,
    CollisionPolygonGenerateRequest,
    CollisionPolygonPatch,
    TileSetCreateRequest,
    TileSetDefinition,
    TileSetPatch,
)
from app.services.asset_library import AssetLibrary, utc_now


class Asset2DResourceService:
    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace)
        self.library = AssetLibrary(self.workspace)
        self._init_schema()

    def _init_schema(self) -> None:
        with self.library._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS asset_collision_polygons (
                    asset_id TEXT PRIMARY KEY,
                    points_json TEXT NOT NULL,
                    source TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE CASCADE
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS asset_animation_clips (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    frame_asset_ids_json TEXT NOT NULL,
                    fps REAL NOT NULL,
                    loop INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS asset_tilesets (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    tile_asset_ids_json TEXT NOT NULL,
                    tile_width INTEGER NOT NULL,
                    tile_height INTEGER NOT NULL,
                    terrain_tags_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    # ----------------------------- collision polygon -----------------------------

    def get_polygon(self, asset_id: str) -> CollisionPolygon | None:
        self.library.get(asset_id)
        with self.library._connect() as db:
            row = db.execute(
                "SELECT * FROM asset_collision_polygons WHERE asset_id=?",
                (asset_id,),
            ).fetchone()
        if row is None:
            return None
        return self._hydrate_polygon(row)

    def set_polygon(self, asset_id: str, patch: CollisionPolygonPatch, *, source: str = "manual") -> CollisionPolygon:
        self.library.get(asset_id)
        points = self._normalize_polygon_points(patch.points)
        now = utc_now()
        payload = json.dumps([point.model_dump() for point in points], ensure_ascii=False)
        with self.library._connect() as db:
            db.execute(
                """
                INSERT INTO asset_collision_polygons(asset_id,points_json,source,updated_at)
                VALUES (?,?,?,?)
                ON CONFLICT(asset_id) DO UPDATE SET
                    points_json=excluded.points_json,
                    source=excluded.source,
                    updated_at=excluded.updated_at
                """,
                (asset_id, payload, source, now),
            )
        polygon = self.get_polygon(asset_id)
        assert polygon is not None
        return polygon

    def generate_polygon(self, asset_id: str, request: CollisionPolygonGenerateRequest) -> CollisionPolygon:
        asset = self.library.get(asset_id)
        mask_path = asset.mask_path or asset.alpha_path or asset.image_path
        path = self.workspace / mask_path
        if not path.is_file():
            raise ValueError("Active asset mask/alpha/image is missing")
        with Image.open(path) as image:
            if mask_path == asset.image_path:
                layer = image.convert("RGBA").getchannel("A")
            else:
                layer = image.convert("L")
            mask = np.asarray(layer, dtype=np.uint8) > request.alpha_threshold
        if mask.ndim != 2 or not mask.any():
            raise ValueError("Cannot generate polygon from an empty mask")
        points = self._convex_hull_from_mask(mask, request.max_points)
        return self.set_polygon(
            asset_id,
            CollisionPolygonPatch(points=points),
            source="mask_convex_hull",
        )

    # -------------------------------- animation ---------------------------------

    def create_animation(self, request: AnimationClipCreateRequest) -> AnimationClip:
        name = request.name.strip()
        if not name:
            raise ValueError("Animation name cannot be empty")
        self._validate_assets(request.frame_asset_ids)
        now = utc_now()
        clip_id = f"anim_{uuid4().hex[:12]}"
        with self.library._connect() as db:
            db.execute(
                """
                INSERT INTO asset_animation_clips(
                    id,name,frame_asset_ids_json,fps,loop,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?)
                """,
                (
                    clip_id,
                    name,
                    json.dumps(request.frame_asset_ids),
                    float(request.fps),
                    int(request.loop),
                    now,
                    now,
                ),
            )
        return self.get_animation(clip_id)

    def get_animation(self, clip_id: str) -> AnimationClip:
        with self.library._connect() as db:
            row = db.execute("SELECT * FROM asset_animation_clips WHERE id=?", (clip_id,)).fetchone()
        if row is None:
            raise FileNotFoundError(clip_id)
        return self._hydrate_animation(row)

    def list_animations(self) -> list[AnimationClip]:
        with self.library._connect() as db:
            rows = db.execute("SELECT * FROM asset_animation_clips ORDER BY updated_at DESC, id").fetchall()
        return [self._hydrate_animation(row) for row in rows]

    def patch_animation(self, clip_id: str, patch: AnimationClipPatch) -> AnimationClip:
        current = self.get_animation(clip_id)
        values = patch.model_dump(exclude_unset=True)
        if "name" in values:
            values["name"] = (values["name"] or "").strip()
            if not values["name"]:
                raise ValueError("Animation name cannot be empty")
        if "frame_asset_ids" in values:
            self._validate_assets(values["frame_asset_ids"])
            values["frame_asset_ids_json"] = json.dumps(values.pop("frame_asset_ids"))
        if "loop" in values:
            values["loop"] = int(bool(values["loop"]))
        if not values:
            return current
        values["updated_at"] = utc_now()
        with self.library._connect() as db:
            assignments = ", ".join(f"{key}=?" for key in values)
            db.execute(
                f"UPDATE asset_animation_clips SET {assignments} WHERE id=?",
                [*values.values(), clip_id],
            )
        return self.get_animation(clip_id)

    # --------------------------------- tilesets ---------------------------------

    def create_tileset(self, request: TileSetCreateRequest) -> TileSetDefinition:
        name = request.name.strip()
        if not name:
            raise ValueError("TileSet name cannot be empty")
        asset_ids = list(dict.fromkeys(request.tile_asset_ids))
        self._validate_assets(asset_ids)
        now = utc_now()
        tileset_id = f"tileset_{uuid4().hex[:12]}"
        tags = self._clean_tags(request.terrain_tags)
        with self.library._connect() as db:
            db.execute(
                """
                INSERT INTO asset_tilesets(
                    id,name,tile_asset_ids_json,tile_width,tile_height,
                    terrain_tags_json,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    tileset_id,
                    name,
                    json.dumps(asset_ids),
                    request.tile_width,
                    request.tile_height,
                    json.dumps(tags, ensure_ascii=False),
                    now,
                    now,
                ),
            )
        return self.get_tileset(tileset_id)

    def get_tileset(self, tileset_id: str) -> TileSetDefinition:
        with self.library._connect() as db:
            row = db.execute("SELECT * FROM asset_tilesets WHERE id=?", (tileset_id,)).fetchone()
        if row is None:
            raise FileNotFoundError(tileset_id)
        return self._hydrate_tileset(row)

    def list_tilesets(self) -> list[TileSetDefinition]:
        with self.library._connect() as db:
            rows = db.execute("SELECT * FROM asset_tilesets ORDER BY updated_at DESC, id").fetchall()
        return [self._hydrate_tileset(row) for row in rows]

    def patch_tileset(self, tileset_id: str, patch: TileSetPatch) -> TileSetDefinition:
        current = self.get_tileset(tileset_id)
        values = patch.model_dump(exclude_unset=True)
        if "name" in values:
            values["name"] = (values["name"] or "").strip()
            if not values["name"]:
                raise ValueError("TileSet name cannot be empty")
        if "tile_asset_ids" in values:
            ids = list(dict.fromkeys(values.pop("tile_asset_ids")))
            self._validate_assets(ids)
            values["tile_asset_ids_json"] = json.dumps(ids)
        if "terrain_tags" in values:
            values["terrain_tags_json"] = json.dumps(
                self._clean_tags(values.pop("terrain_tags") or []),
                ensure_ascii=False,
            )
        if not values:
            return current
        values["updated_at"] = utc_now()
        with self.library._connect() as db:
            assignments = ", ".join(f"{key}=?" for key in values)
            db.execute(
                f"UPDATE asset_tilesets SET {assignments} WHERE id=?",
                [*values.values(), tileset_id],
            )
        return self.get_tileset(tileset_id)

    # --------------------------------- helpers ----------------------------------

    def _validate_assets(self, asset_ids: list[str]) -> None:
        for asset_id in asset_ids:
            self.library.get(asset_id)

    @staticmethod
    def _clean_tags(values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for raw in values:
            value = raw.strip()
            key = value.lower()
            if value and key not in seen:
                seen.add(key)
                result.append(value)
        return result

    @staticmethod
    def _normalize_polygon_points(points: list[CollisionPoint]) -> list[CollisionPoint]:
        result: list[CollisionPoint] = []
        for point in points:
            if result and abs(result[-1].x - point.x) < 1e-8 and abs(result[-1].y - point.y) < 1e-8:
                continue
            result.append(point)
        if len(result) >= 2 and abs(result[0].x - result[-1].x) < 1e-8 and abs(result[0].y - result[-1].y) < 1e-8:
            result.pop()
        if len(result) < 3:
            raise ValueError("Collision polygon requires at least three unique points")
        return result

    @staticmethod
    def _convex_hull_from_mask(mask: np.ndarray, max_points: int) -> list[CollisionPoint]:
        height, width = mask.shape
        candidates: list[tuple[int, int]] = []
        rows = np.flatnonzero(mask.any(axis=1))
        for y in rows.tolist():
            xs = np.flatnonzero(mask[y])
            if xs.size:
                candidates.append((int(xs[0]), y))
                if xs[-1] != xs[0]:
                    candidates.append((int(xs[-1]), y))
        points = sorted(set(candidates))
        if len(points) < 3:
            ys, xs = np.nonzero(mask)
            if len(xs) < 3:
                raise ValueError("Mask is too small to form a collision polygon")
            points = sorted(set(zip(xs.tolist(), ys.tolist())))

        def cross(o: tuple[int, int], a: tuple[int, int], b: tuple[int, int]) -> int:
            return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

        lower: list[tuple[int, int]] = []
        for point in points:
            while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
                lower.pop()
            lower.append(point)
        upper: list[tuple[int, int]] = []
        for point in reversed(points):
            while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
                upper.pop()
            upper.append(point)
        hull = lower[:-1] + upper[:-1]
        if len(hull) < 3:
            raise ValueError("Mask hull is degenerate")
        if len(hull) > max_points:
            indices = np.linspace(0, len(hull) - 1, max_points, dtype=int)
            hull = [hull[index] for index in sorted(set(indices.tolist()))]
        denom_x = max(1, width - 1)
        denom_y = max(1, height - 1)
        return [CollisionPoint(x=x / denom_x, y=y / denom_y) for x, y in hull]

    @staticmethod
    def _hydrate_polygon(row) -> CollisionPolygon:
        return CollisionPolygon(
            asset_id=row["asset_id"],
            points=[CollisionPoint(**item) for item in json.loads(row["points_json"])],
            source=row["source"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _hydrate_animation(row) -> AnimationClip:
        return AnimationClip(
            id=row["id"],
            name=row["name"],
            frame_asset_ids=json.loads(row["frame_asset_ids_json"]),
            fps=float(row["fps"]),
            loop=bool(row["loop"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _hydrate_tileset(row) -> TileSetDefinition:
        return TileSetDefinition(
            id=row["id"],
            name=row["name"],
            tile_asset_ids=json.loads(row["tile_asset_ids_json"]),
            tile_width=int(row["tile_width"]),
            tile_height=int(row["tile_height"]),
            terrain_tags=json.loads(row["terrain_tags_json"] or "[]"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
