from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from uuid import uuid4

import numpy as np
from PIL import Image

from app.asset_2d_models import (
    AnimationClip,
    AnimationClipCreateRequest,
    AnimationClipPatch,
    AnimationFrameSequenceRequest,
    AutoTileMode,
    CollisionPoint,
    CollisionPolygon,
    CollisionPolygonGenerateRequest,
    CollisionPolygonPatch,
    TileSetCreateRequest,
    TileSetDefinition,
    TileSetPatch,
    TileTerrainRule,
)
from app.services.asset_library import AssetLibrary, utc_now


class Asset2DResourceService:
    # Neighbor bit order is clockwise from north:
    # N=1, NE=2, E=4, SE=8, S=16, SW=32, W=64, NW=128.
    CARDINAL_MASK = 1 | 4 | 16 | 64

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
                    autotile_mode TEXT NOT NULL DEFAULT 'none',
                    terrain_rules_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            columns = {row["name"] for row in db.execute("PRAGMA table_info(asset_tilesets)").fetchall()}
            if "autotile_mode" not in columns:
                db.execute("ALTER TABLE asset_tilesets ADD COLUMN autotile_mode TEXT NOT NULL DEFAULT 'none'")
            if "terrain_rules_json" not in columns:
                db.execute("ALTER TABLE asset_tilesets ADD COLUMN terrain_rules_json TEXT NOT NULL DEFAULT '[]'")

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

    def set_animation_frames(self, clip_id: str, request: AnimationFrameSequenceRequest) -> AnimationClip:
        current = self.get_animation(clip_id)
        self._validate_assets(request.frame_asset_ids)
        if request.require_same_frames and Counter(current.frame_asset_ids) != Counter(request.frame_asset_ids):
            raise ValueError("Frame reorder must preserve the same frame multiset")
        return self.patch_animation(
            clip_id,
            AnimationClipPatch(frame_asset_ids=request.frame_asset_ids),
        )

    # --------------------------------- tilesets ---------------------------------

    def create_tileset(self, request: TileSetCreateRequest) -> TileSetDefinition:
        name = request.name.strip()
        if not name:
            raise ValueError("TileSet name cannot be empty")
        asset_ids = list(dict.fromkeys(request.tile_asset_ids))
        self._validate_assets(asset_ids)
        mode = request.autotile_mode
        rules = self._normalize_terrain_rules(asset_ids, mode, request.terrain_rules)
        tags = self._clean_tags([*request.terrain_tags, *(rule.terrain for rule in rules)])
        now = utc_now()
        tileset_id = f"tileset_{uuid4().hex[:12]}"
        with self.library._connect() as db:
            db.execute(
                """
                INSERT INTO asset_tilesets(
                    id,name,tile_asset_ids_json,tile_width,tile_height,
                    terrain_tags_json,autotile_mode,terrain_rules_json,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    tileset_id,
                    name,
                    json.dumps(asset_ids),
                    request.tile_width,
                    request.tile_height,
                    json.dumps(tags, ensure_ascii=False),
                    mode.value,
                    json.dumps([rule.model_dump(mode="json") for rule in rules], ensure_ascii=False),
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

        asset_ids = values.pop("tile_asset_ids", current.tile_asset_ids)
        asset_ids = list(dict.fromkeys(asset_ids))
        self._validate_assets(asset_ids)
        mode_value = values.pop("autotile_mode", current.autotile_mode)
        mode = mode_value if isinstance(mode_value, AutoTileMode) else AutoTileMode(mode_value)
        rules_value = values.pop("terrain_rules", current.terrain_rules)
        rules = [item if isinstance(item, TileTerrainRule) else TileTerrainRule(**item) for item in rules_value]
        rules = self._normalize_terrain_rules(asset_ids, mode, rules)

        tags_value = values.pop("terrain_tags", current.terrain_tags)
        tags = self._clean_tags([*tags_value, *(rule.terrain for rule in rules)])
        values.update(
            {
                "tile_asset_ids_json": json.dumps(asset_ids),
                "terrain_tags_json": json.dumps(tags, ensure_ascii=False),
                "autotile_mode": mode.value,
                "terrain_rules_json": json.dumps(
                    [rule.model_dump(mode="json") for rule in rules],
                    ensure_ascii=False,
                ),
            }
        )
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

    def _normalize_terrain_rules(
        self,
        asset_ids: list[str],
        mode: AutoTileMode,
        rules: list[TileTerrainRule],
    ) -> list[TileTerrainRule]:
        if rules and mode == AutoTileMode.NONE:
            raise ValueError("Autotile terrain rules require cardinal4 or eight8 mode")
        allowed_assets = set(asset_ids)
        result: list[TileTerrainRule] = []
        seen_assets: set[str] = set()
        for raw in rules:
            rule = raw if isinstance(raw, TileTerrainRule) else TileTerrainRule(**raw)
            if rule.asset_id not in allowed_assets:
                raise ValueError(f"Terrain rule asset {rule.asset_id!r} is not part of the TileSet")
            terrain = rule.terrain.strip()
            if not terrain:
                raise ValueError("Terrain rule terrain cannot be empty")
            if rule.asset_id in seen_assets:
                raise ValueError(f"Only one autotile rule is allowed per tile asset: {rule.asset_id}")
            if mode == AutoTileMode.CARDINAL4 and rule.neighbor_mask & ~self.CARDINAL_MASK:
                raise ValueError("cardinal4 rules may only use N/E/S/W neighbor bits")
            seen_assets.add(rule.asset_id)
            result.append(
                TileTerrainRule(
                    asset_id=rule.asset_id,
                    terrain=terrain,
                    neighbor_mask=rule.neighbor_mask,
                    priority=rule.priority,
                )
            )
        result.sort(key=lambda item: (-item.priority, item.asset_id))
        return result

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
        keys = set(row.keys())
        mode = AutoTileMode(row["autotile_mode"] if "autotile_mode" in keys else "none")
        rules_payload = json.loads(row["terrain_rules_json"] or "[]") if "terrain_rules_json" in keys else []
        return TileSetDefinition(
            id=row["id"],
            name=row["name"],
            tile_asset_ids=json.loads(row["tile_asset_ids_json"]),
            tile_width=int(row["tile_width"]),
            tile_height=int(row["tile_height"]),
            terrain_tags=json.loads(row["terrain_tags_json"] or "[]"),
            autotile_mode=mode,
            terrain_rules=[TileTerrainRule(**item) for item in rules_payload],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
