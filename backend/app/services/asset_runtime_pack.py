from __future__ import annotations

import json
import zipfile
from pathlib import Path

from app.asset_runtime_models import (
    CollisionMode,
    RuntimeAssetPackExportRequest,
    RuntimeAssetPackExportResult,
)
from app.services.asset_library_workflow import AssetLibraryWorkflowService
from app.services.asset_runtime_config import AssetRuntimeConfigService
from app.services.pipeline import AssetSplitPipeline


class AssetRuntimePackService:
    def __init__(self, workspace: str | Path, pipeline: AssetSplitPipeline) -> None:
        self.workspace = Path(workspace)
        self.workflow = AssetLibraryWorkflowService(self.workspace, pipeline)
        self.runtime = AssetRuntimeConfigService(self.workspace)

    def export(self, request: RuntimeAssetPackExportRequest) -> RuntimeAssetPackExportResult:
        base = self.workflow.export_pack(request)
        pack_dir = self.workflow.state_root / base.pack_id
        manifest_path = Path(base.manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        asset_ids = [item["id"] for item in manifest.get("assets", [])]
        configs = self.runtime.snapshot(asset_ids) if request.include_runtime_config else []
        config_by_id = {item.asset_id: item for item in configs}

        runtime_doc = {
            "schema": "game-creater/runtime-config/v1",
            "pack_id": base.pack_id,
            "assets": [item.model_dump(mode="json") for item in configs],
        }
        (pack_dir / "runtime_config.json").write_text(
            json.dumps(runtime_doc, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        for entry in manifest.get("assets", []):
            config = config_by_id.get(entry["id"])
            if config is not None:
                entry["runtime"] = config.model_dump(mode="json")
        manifest["runtime_schema"] = runtime_doc["schema"]
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        if request.engine.value == "godot4":
            self._write_godot_runtime(pack_dir / "godot4", manifest.get("assets", []), config_by_id)
        elif request.engine.value == "unity2d":
            self._write_unity_runtime(pack_dir / "unity2d", runtime_doc)

        self._rebuild_archive(pack_dir, Path(base.archive_path))
        return RuntimeAssetPackExportResult(
            **base.model_dump(),
            runtime_config_count=len(configs),
        )

    def _write_godot_runtime(self, root: Path, assets: list[dict], config_by_id: dict) -> None:
        # Existing v1 AtlasTexture files assumed assets lived at res://assets. Runtime
        # packs are extracted as /godot4 under the project root, so fix those paths.
        for tres in (root / "resources").glob("*.tres") if (root / "resources").exists() else []:
            text = tres.read_text(encoding="utf-8")
            tres.write_text(text.replace("res://assets/", "res://godot4/assets/"), encoding="utf-8")

        scenes = root / "prefabs"
        scenes.mkdir(parents=True, exist_ok=True)
        by_id = {item["id"]: item for item in assets}
        for asset_id, config in config_by_id.items():
            asset = by_id.get(asset_id)
            if not asset:
                continue
            width = int(asset.get("width") or 1)
            height = int(asset.get("height") or 1)
            offset_x = (0.5 - config.pivot_x) * width
            offset_y = (0.5 - config.pivot_y) * height
            load_steps = 3 if config.collision_mode == CollisionMode.BOX else 2
            lines = [
                f"[gd_scene load_steps={load_steps} format=3]",
                "",
                f'[ext_resource type="Texture2D" path="res://godot4/assets/{asset_id}.png" id="1_tex"]',
            ]
            if config.collision_mode == CollisionMode.BOX:
                lines += [
                    "",
                    '[sub_resource type="RectangleShape2D" id="1_shape"]',
                    f"size = Vector2({width}, {height})",
                ]
            lines += [
                "",
                f'[node name="{self._godot_name(asset.get("name") or asset_id)}" type="Node2D"]',
                f"z_index = {config.sorting_order}",
                "",
                '[node name="Sprite2D" type="Sprite2D" parent="."]',
                'texture = ExtResource("1_tex")',
                f"offset = Vector2({offset_x:.4f}, {offset_y:.4f})",
            ]
            if config.collision_mode == CollisionMode.BOX:
                body_type = "Area2D" if config.collision_is_trigger else "StaticBody2D"
                lines += [
                    "",
                    f'[node name="CollisionBody" type="{body_type}" parent="."]',
                    "",
                    '[node name="CollisionShape2D" type="CollisionShape2D" parent="CollisionBody"]',
                    f"position = Vector2({offset_x:.4f}, {offset_y:.4f})",
                    'shape = SubResource("1_shape")',
                ]
            (scenes / f"{asset_id}.tscn").write_text("\n".join(lines) + "\n", encoding="utf-8")

        (root / "RUNTIME_IMPORT.md").write_text(
            "Extract the `godot4` folder at your Godot project root. `prefabs/*.tscn` contain Sprite2D pivot offsets, z_index and optional box collision generated from Game Creater runtime config.\n",
            encoding="utf-8",
        )

    @staticmethod
    def _write_unity_runtime(root: Path, runtime_doc: dict) -> None:
        pack_root = root / "Assets" / "GameCreaterPack"
        pack_root.mkdir(parents=True, exist_ok=True)
        (pack_root / "runtime_config.json").write_text(
            json.dumps(runtime_doc, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        runtime_dir = pack_root / "Runtime"
        editor_dir = pack_root / "Editor"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        editor_dir.mkdir(parents=True, exist_ok=True)
        (runtime_dir / "GameCreaterRuntimeMetadata.cs").write_text(
            r'''using UnityEngine;

public class GameCreaterRuntimeMetadata : MonoBehaviour
{
    public string assetId;
    public string renderLayer;
    public string[] gameplayTags;
}
''',
            encoding="utf-8",
        )
        (editor_dir / "GameCreaterRuntimePrefabBuilder.cs").write_text(
            r'''using System;
using System.IO;
using UnityEditor;
using UnityEngine;

[Serializable]
public class GameCreaterRuntimeConfigRoot { public string schema; public string pack_id; public GameCreaterRuntimeItem[] assets; }

[Serializable]
public class GameCreaterRuntimeItem
{
    public string asset_id;
    public float pivot_x;
    public float pivot_y;
    public float pixels_per_unit;
    public string render_layer;
    public int sorting_order;
    public string collision_mode;
    public bool collision_is_trigger;
    public string[] gameplay_tags;
}

public static class GameCreaterRuntimePrefabBuilder
{
    [MenuItem("Game Creater/Build Runtime Asset Prefabs")]
    public static void Build()
    {
        const string root = "Assets/GameCreaterPack";
        var json = File.ReadAllText(Path.Combine(root, "runtime_config.json"));
        var config = JsonUtility.FromJson<GameCreaterRuntimeConfigRoot>(json);
        Directory.CreateDirectory(Path.Combine(root, "Prefabs"));

        foreach (var item in config.assets)
        {
            var texturePath = $"{root}/assets/{item.asset_id}.png";
            if (AssetImporter.GetAtPath(texturePath) is TextureImporter importer)
            {
                importer.textureType = TextureImporterType.Sprite;
                importer.spriteImportMode = SpriteImportMode.Single;
                importer.spritePixelsPerUnit = item.pixels_per_unit;
                importer.spriteAlignment = (int)SpriteAlignment.Custom;
                importer.spritePivot = new Vector2(item.pivot_x, item.pivot_y);
                importer.alphaIsTransparency = true;
                importer.mipmapEnabled = false;
                importer.SaveAndReimport();
            }

            var sprite = AssetDatabase.LoadAssetAtPath<Sprite>(texturePath);
            if (sprite == null) continue;
            var go = new GameObject(item.asset_id);
            var renderer = go.AddComponent<SpriteRenderer>();
            renderer.sprite = sprite;
            renderer.sortingOrder = item.sorting_order;
            var metadata = go.AddComponent<GameCreaterRuntimeMetadata>();
            metadata.assetId = item.asset_id;
            metadata.renderLayer = item.render_layer;
            metadata.gameplayTags = item.gameplay_tags;
            if (item.collision_mode == "box")
            {
                var collider = go.AddComponent<BoxCollider2D>();
                collider.isTrigger = item.collision_is_trigger;
            }
            PrefabUtility.SaveAsPrefabAsset(go, $"{root}/Prefabs/{item.asset_id}.prefab");
            UnityEngine.Object.DestroyImmediate(go);
        }
        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();
        Debug.Log($"Game Creater: built {config.assets.Length} runtime asset prefabs.");
    }
}
''',
            encoding="utf-8",
        )

    @staticmethod
    def _rebuild_archive(pack_dir: Path, archive_path: Path) -> None:
        archive_path.unlink(missing_ok=True)
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(pack_dir.rglob("*")):
                if path.is_file():
                    archive.write(path, arcname=path.relative_to(pack_dir))

    @staticmethod
    def _godot_name(value: str) -> str:
        clean = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in value).strip("_")
        return clean or "GameAsset"
