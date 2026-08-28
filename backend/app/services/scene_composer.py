from __future__ import annotations

import json
import re
import shutil
import sqlite3
import zipfile
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from app.scene_composer_models import (
    ComposerExportResult,
    ComposerExportTarget,
    ComposerItem,
    ComposerItemCreate,
    ComposerItemPatch,
    ComposerLayer,
    ComposerLayerCreate,
    ComposerLayerPatch,
    ComposerScene,
    ComposerSceneCreate,
    ComposerScenePatch,
    ComposerTransform,
)
from app.services.asset_library import AssetLibrary, LibraryAssetNotFoundError, utc_now


class ComposerSceneNotFoundError(KeyError):
    pass


class ComposerLayerNotFoundError(KeyError):
    pass


class ComposerItemNotFoundError(KeyError):
    pass


class SceneComposerService:
    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace)
        self.library = AssetLibrary(self.workspace)
        self.state_root = self.workspace.parent / ".game_creater_state"
        self.export_root = self.state_root / "composer_exports"
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.export_root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.state_root / "scene_composer.db"
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
                CREATE TABLE IF NOT EXISTS composer_scenes (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    grid_size INTEGER NOT NULL,
                    background TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS composer_layers (
                    id TEXT PRIMARY KEY,
                    scene_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    layer_order INTEGER NOT NULL,
                    visible INTEGER NOT NULL DEFAULT 1,
                    locked INTEGER NOT NULL DEFAULT 0,
                    y_sort INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(scene_id) REFERENCES composer_scenes(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS composer_items (
                    id TEXT PRIMARY KEY,
                    scene_id TEXT NOT NULL,
                    layer_id TEXT NOT NULL,
                    asset_id TEXT NOT NULL,
                    x REAL NOT NULL,
                    y REAL NOT NULL,
                    rotation_deg REAL NOT NULL,
                    scale_x REAL NOT NULL,
                    scale_y REAL NOT NULL,
                    z_index INTEGER NOT NULL,
                    visible INTEGER NOT NULL DEFAULT 1,
                    locked INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(scene_id) REFERENCES composer_scenes(id) ON DELETE CASCADE,
                    FOREIGN KEY(layer_id) REFERENCES composer_layers(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_composer_layers_scene ON composer_layers(scene_id, layer_order);
                CREATE INDEX IF NOT EXISTS idx_composer_items_scene ON composer_items(scene_id, layer_id);
                """
            )

    def create_scene(self, request: ComposerSceneCreate) -> ComposerScene:
        name = request.name.strip()
        if not name:
            raise ValueError("Scene name cannot be empty")
        scene_id = f"cmp_{uuid4().hex[:12]}"
        layer_id = f"layer_{uuid4().hex[:12]}"
        now = utc_now()
        with self._connect() as db:
            db.execute(
                "INSERT INTO composer_scenes(id,name,width,height,grid_size,background,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (scene_id, name, request.width, request.height, request.grid_size, request.background, now, now),
            )
            db.execute(
                "INSERT INTO composer_layers(id,scene_id,name,layer_order,visible,locked,y_sort) VALUES (?,?,?,?,1,0,0)",
                (layer_id, scene_id, "Default", 0),
            )
        return self.get_scene(scene_id)

    def list_scenes(self) -> list[ComposerScene]:
        with self._connect() as db:
            rows = db.execute("SELECT id FROM composer_scenes ORDER BY updated_at DESC, id").fetchall()
        return [self.get_scene(row["id"]) for row in rows]

    def get_scene(self, scene_id: str) -> ComposerScene:
        with self._connect() as db:
            row = db.execute("SELECT * FROM composer_scenes WHERE id=?", (scene_id,)).fetchone()
            if row is None:
                raise ComposerSceneNotFoundError(scene_id)
            layer_rows = db.execute(
                "SELECT * FROM composer_layers WHERE scene_id=? ORDER BY layer_order, id",
                (scene_id,),
            ).fetchall()
            item_rows = db.execute(
                "SELECT * FROM composer_items WHERE scene_id=? ORDER BY z_index, created_at, id",
                (scene_id,),
            ).fetchall()
        return ComposerScene(
            id=row["id"],
            name=row["name"],
            width=row["width"],
            height=row["height"],
            grid_size=row["grid_size"],
            background=row["background"],
            layers=[self._layer_from_row(item) for item in layer_rows],
            items=[self._item_from_row(item) for item in item_rows],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def patch_scene(self, scene_id: str, patch: ComposerScenePatch) -> ComposerScene:
        self.get_scene(scene_id)
        values = patch.model_dump(exclude_unset=True)
        if "name" in values:
            values["name"] = (values["name"] or "").strip()
            if not values["name"]:
                raise ValueError("Scene name cannot be empty")
        if not values:
            return self.get_scene(scene_id)
        values["updated_at"] = utc_now()
        with self._connect() as db:
            assignments = ", ".join(f"{key}=?" for key in values)
            db.execute(f"UPDATE composer_scenes SET {assignments} WHERE id=?", [*values.values(), scene_id])
        return self.get_scene(scene_id)

    def add_layer(self, scene_id: str, request: ComposerLayerCreate) -> ComposerScene:
        self.get_scene(scene_id)
        name = request.name.strip()
        if not name:
            raise ValueError("Layer name cannot be empty")
        layer_id = f"layer_{uuid4().hex[:12]}"
        with self._connect() as db:
            order = db.execute(
                "SELECT COALESCE(MAX(layer_order), -1) + 1 AS n FROM composer_layers WHERE scene_id=?",
                (scene_id,),
            ).fetchone()["n"]
            db.execute(
                "INSERT INTO composer_layers(id,scene_id,name,layer_order,visible,locked,y_sort) VALUES (?,?,?,?,1,0,?)",
                (layer_id, scene_id, name, int(order), int(request.y_sort)),
            )
            db.execute("UPDATE composer_scenes SET updated_at=? WHERE id=?", (utc_now(), scene_id))
        return self.get_scene(scene_id)

    def patch_layer(self, scene_id: str, layer_id: str, patch: ComposerLayerPatch) -> ComposerScene:
        self._require_layer(scene_id, layer_id)
        values = patch.model_dump(exclude_unset=True)
        if "name" in values:
            values["name"] = (values["name"] or "").strip()
            if not values["name"]:
                raise ValueError("Layer name cannot be empty")
        if "order" in values:
            values["layer_order"] = values.pop("order")
        for key in ("visible", "locked", "y_sort"):
            if key in values:
                values[key] = int(bool(values[key]))
        with self._connect() as db:
            if values:
                assignments = ", ".join(f"{key}=?" for key in values)
                db.execute(f"UPDATE composer_layers SET {assignments} WHERE id=? AND scene_id=?", [*values.values(), layer_id, scene_id])
            db.execute("UPDATE composer_scenes SET updated_at=? WHERE id=?", (utc_now(), scene_id))
        return self.get_scene(scene_id)

    def add_item(self, scene_id: str, request: ComposerItemCreate) -> ComposerScene:
        scene = self.get_scene(scene_id)
        self.library.get(request.asset_id)
        layer_id = request.layer_id or scene.layers[0].id
        self._require_layer(scene_id, layer_id)
        item_id = f"item_{uuid4().hex[:12]}"
        now = utc_now()
        t = request.transform
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO composer_items(
                    id,scene_id,layer_id,asset_id,x,y,rotation_deg,scale_x,scale_y,z_index,visible,locked,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,1,0,?,?)
                """,
                (item_id, scene_id, layer_id, request.asset_id, t.x, t.y, t.rotation_deg, t.scale_x, t.scale_y, request.z_index, now, now),
            )
            db.execute("UPDATE composer_scenes SET updated_at=? WHERE id=?", (now, scene_id))
        return self.get_scene(scene_id)

    def patch_item(self, scene_id: str, item_id: str, patch: ComposerItemPatch) -> ComposerScene:
        self._require_item(scene_id, item_id)
        values = patch.model_dump(exclude_unset=True)
        transform = values.pop("transform", None)
        if "layer_id" in values and values["layer_id"] is not None:
            self._require_layer(scene_id, values["layer_id"])
        if transform is not None:
            transform = transform if isinstance(transform, dict) else transform.model_dump()
            values.update(transform)
        for key in ("visible", "locked"):
            if key in values:
                values[key] = int(bool(values[key]))
        values = {key: value for key, value in values.items() if value is not None}
        now = utc_now()
        with self._connect() as db:
            if values:
                values["updated_at"] = now
                assignments = ", ".join(f"{key}=?" for key in values)
                db.execute(f"UPDATE composer_items SET {assignments} WHERE id=? AND scene_id=?", [*values.values(), item_id, scene_id])
            db.execute("UPDATE composer_scenes SET updated_at=? WHERE id=?", (now, scene_id))
        return self.get_scene(scene_id)

    def delete_item(self, scene_id: str, item_id: str) -> ComposerScene:
        self._require_item(scene_id, item_id)
        with self._connect() as db:
            db.execute("DELETE FROM composer_items WHERE id=? AND scene_id=?", (item_id, scene_id))
            db.execute("UPDATE composer_scenes SET updated_at=? WHERE id=?", (utc_now(), scene_id))
        return self.get_scene(scene_id)

    def export(self, scene_id: str, target: ComposerExportTarget) -> ComposerExportResult:
        scene = self.get_scene(scene_id)
        pack_dir = self.export_root / f"{scene.id}_{target.value}"
        if pack_dir.exists():
            shutil.rmtree(pack_dir)
        pack_dir.mkdir(parents=True, exist_ok=True)
        assets_dir = pack_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        copied: set[str] = set()
        for item in scene.items:
            if item.asset_id in copied:
                continue
            asset = self.library.get(item.asset_id)
            source = self.workspace / asset.image_path
            if not source.is_file():
                raise FileNotFoundError(f"Missing active image for {item.asset_id}")
            shutil.copy2(source, assets_dir / f"{item.asset_id}.png")
            copied.add(item.asset_id)

        scene_doc = scene.model_dump(mode="json")
        (pack_dir / "scene_composer.json").write_text(json.dumps(scene_doc, ensure_ascii=False, indent=2), encoding="utf-8")
        if target == ComposerExportTarget.GODOT4:
            self._write_godot(pack_dir, scene)
        elif target == ComposerExportTarget.UNITY2D:
            self._write_unity(pack_dir, scene)

        archive = self.export_root / f"{scene.id}_{target.value}.zip"
        archive.unlink(missing_ok=True)
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
            for path in sorted(pack_dir.rglob("*")):
                if path.is_file():
                    output.write(path, path.relative_to(pack_dir))
        return ComposerExportResult(
            scene_id=scene.id,
            target=target,
            archive_path=str(archive),
            download_url=f"/api/v1/library/composer/exports/{scene.id}/{target.value}",
        )

    def export_path(self, scene_id: str, target: ComposerExportTarget) -> Path:
        path = self.export_root / f"{scene_id}_{target.value}.zip"
        if not path.is_file():
            raise FileNotFoundError(path)
        return path

    def _write_godot(self, root: Path, scene: ComposerScene) -> None:
        lines = ["[gd_scene format=3]", ""]
        unique = list(dict.fromkeys(item.asset_id for item in scene.items))
        resource_ids = {asset_id: index + 1 for index, asset_id in enumerate(unique)}
        for asset_id in unique:
            lines.append(f'[ext_resource type="Texture2D" path="res://assets/{asset_id}.png" id="{resource_ids[asset_id]}_tex"]')
        lines += ["", f'[node name="{self._safe_name(scene.name)}" type="Node2D"]']
        layer_by_id = {layer.id: layer for layer in scene.layers}
        for item in scene.items:
            if not item.visible:
                continue
            layer = layer_by_id[item.layer_id]
            if not layer.visible:
                continue
            t = item.transform
            order = layer.order * 10000 + item.z_index
            lines += [
                "",
                f'[node name="{self._safe_name(item.asset_name)}_{item.id[-4:]}" type="Sprite2D" parent="."]',
                f'texture = ExtResource("{resource_ids[item.asset_id]}_tex")',
                f"position = Vector2({t.x:.4f}, {t.y:.4f})",
                f"rotation_degrees = {t.rotation_deg:.4f}",
                f"scale = Vector2({t.scale_x:.6f}, {t.scale_y:.6f})",
                f"z_index = {order}",
                f"y_sort_enabled = {'true' if layer.y_sort else 'false'}",
            ]
        (root / "scene.tscn").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (root / "project.godot").write_text(
            '[application]\nconfig/name="Game Creater Composer"\nrun/main_scene="res://scene.tscn"\n\n[display]\nwindow/size/viewport_width=%d\nwindow/size/viewport_height=%d\n' % (scene.width, scene.height),
            encoding="utf-8",
        )

    @staticmethod
    def _write_unity(root: Path, scene: ComposerScene) -> None:
        unity_root = root / "Assets" / "GameCreaterComposer"
        assets_root = unity_root / "assets"
        assets_root.mkdir(parents=True, exist_ok=True)
        for source in (root / "assets").glob("*.png"):
            shutil.copy2(source, assets_root / source.name)
        (unity_root / "scene_composer.json").write_text(json.dumps(scene.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
        editor = unity_root / "Editor"
        editor.mkdir(parents=True, exist_ok=True)
        editor.joinpath("GameCreaterComposerBuilder.cs").write_text(
            r'''using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

[Serializable] public class GCTransform { public float x; public float y; public float rotation_deg; public float scale_x; public float scale_y; }
[Serializable] public class GCItem { public string id; public string asset_id; public string asset_name; public string layer_id; public GCTransform transform; public int z_index; public bool visible; }
[Serializable] public class GCLayer { public string id; public string name; public int order; public bool visible; public bool y_sort; }
[Serializable] public class GCScene { public string id; public string name; public int width; public int height; public GCLayer[] layers; public GCItem[] items; }

public static class GameCreaterComposerBuilder {
  [MenuItem("Game Creater/Build Composer Scene")]
  public static void Build() {
    const string root = "Assets/GameCreaterComposer";
    var doc = JsonUtility.FromJson<GCScene>(File.ReadAllText(Path.Combine(root, "scene_composer.json")));
    var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
    var layers = new System.Collections.Generic.Dictionary<string, Transform>();
    foreach (var layer in doc.layers) {
      var go = new GameObject(layer.name); go.SetActive(layer.visible); layers[layer.id] = go.transform;
    }
    foreach (var item in doc.items) {
      if (!item.visible) continue;
      var sprite = AssetDatabase.LoadAssetAtPath<Sprite>($"{root}/assets/{item.asset_id}.png");
      if (sprite == null) continue;
      var go = new GameObject(item.asset_name); go.transform.SetParent(layers[item.layer_id], false);
      go.transform.position = new Vector3(item.transform.x / 100f, -item.transform.y / 100f, 0f);
      go.transform.eulerAngles = new Vector3(0f, 0f, -item.transform.rotation_deg);
      go.transform.localScale = new Vector3(item.transform.scale_x, item.transform.scale_y, 1f);
      var renderer = go.AddComponent<SpriteRenderer>(); renderer.sprite = sprite; renderer.sortingOrder = item.z_index;
    }
    Directory.CreateDirectory($"{root}/Scenes");
    EditorSceneManager.SaveScene(scene, $"{root}/Scenes/{doc.id}.unity");
    AssetDatabase.SaveAssets(); AssetDatabase.Refresh();
  }
}
''',
            encoding="utf-8",
        )

    def _require_layer(self, scene_id: str, layer_id: str) -> None:
        with self._connect() as db:
            row = db.execute("SELECT id FROM composer_layers WHERE id=? AND scene_id=?", (layer_id, scene_id)).fetchone()
        if row is None:
            raise ComposerLayerNotFoundError(layer_id)

    def _require_item(self, scene_id: str, item_id: str) -> None:
        with self._connect() as db:
            row = db.execute("SELECT id FROM composer_items WHERE id=? AND scene_id=?", (item_id, scene_id)).fetchone()
        if row is None:
            raise ComposerItemNotFoundError(item_id)

    @staticmethod
    def _layer_from_row(row) -> ComposerLayer:
        return ComposerLayer(
            id=row["id"], name=row["name"], order=int(row["layer_order"]),
            visible=bool(row["visible"]), locked=bool(row["locked"]), y_sort=bool(row["y_sort"]),
        )

    def _item_from_row(self, row) -> ComposerItem:
        try:
            asset = self.library.get(row["asset_id"])
            return ComposerItem(
                id=row["id"], asset_id=row["asset_id"], asset_name=asset.name,
                image_url=f"/workspace/{asset.image_path}", width=asset.width, height=asset.height,
                layer_id=row["layer_id"],
                transform=ComposerTransform(
                    x=row["x"], y=row["y"], rotation_deg=row["rotation_deg"],
                    scale_x=row["scale_x"], scale_y=row["scale_y"],
                ),
                z_index=int(row["z_index"]), visible=bool(row["visible"]), locked=bool(row["locked"]),
            )
        except LibraryAssetNotFoundError as exc:
            raise ValueError(f"Composer item references missing asset: {row['asset_id']}") from exc

    @staticmethod
    def _safe_name(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9_]", "_", value).strip("_") or "Scene"
