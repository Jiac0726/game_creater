from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

from app.asset_2d_models import GameReadyPackExportRequest, GameReadyPackExportResult
from app.asset_runtime_models import CollisionMode
from app.services.asset_2d_resources import Asset2DResourceService
from app.services.asset_runtime_config import AssetRuntimeConfigService
from app.services.asset_runtime_pack import AssetRuntimePackService
from app.services.pipeline import AssetSplitPipeline


class Asset2DGameReadyPackService:
    def __init__(self, workspace: str | Path, pipeline: AssetSplitPipeline) -> None:
        self.workspace = Path(workspace)
        self.resources = Asset2DResourceService(self.workspace)
        self.runtime = AssetRuntimeConfigService(self.workspace)
        self.runtime_pack = AssetRuntimePackService(self.workspace, pipeline)

    def export(self, request: GameReadyPackExportRequest) -> GameReadyPackExportResult:
        animations = [self.resources.get_animation(item) for item in request.animation_ids]
        tilesets = [self.resources.get_tileset(item) for item in request.tileset_ids]

        expanded_ids = list(dict.fromkeys(request.asset_ids))
        for clip in animations:
            expanded_ids.extend(clip.frame_asset_ids)
        for tileset in tilesets:
            expanded_ids.extend(tileset.tile_asset_ids)
        expanded_ids = list(dict.fromkeys(expanded_ids))

        runtime_request = request.model_copy(update={"asset_ids": expanded_ids})
        base = self.runtime_pack.export(runtime_request)
        pack_dir = self.runtime_pack.workflow.state_root / base.pack_id
        manifest = json.loads(Path(base.manifest_path).read_text(encoding="utf-8"))
        asset_by_id = {item["id"]: item for item in manifest.get("assets", [])}
        asset_ids = list(asset_by_id)
        config_by_id = {item.asset_id: item for item in self.runtime.snapshot(asset_ids)}

        polygons = []
        if request.include_collision_polygons:
            for asset_id in asset_ids:
                polygon = self.resources.get_polygon(asset_id)
                config = config_by_id.get(asset_id)
                if polygon is None or config is None or config.collision_mode != CollisionMode.POLYGON:
                    continue
                polygons.append(
                    {
                        **polygon.model_dump(mode="json"),
                        "is_trigger": config.collision_is_trigger,
                        "pivot_x": config.pivot_x,
                        "pivot_y": config.pivot_y,
                        "pixels_per_unit": config.pixels_per_unit,
                    }
                )

        game_ready = {
            "schema": "game-creater/game-ready-2d/v1",
            "pack_id": base.pack_id,
            "collision_polygons": polygons,
            "animations": [item.model_dump(mode="json") for item in animations],
            "tilesets": [item.model_dump(mode="json") for item in tilesets],
        }
        (pack_dir / "game_ready_2d.json").write_text(
            json.dumps(game_ready, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        manifest["game_ready_schema"] = game_ready["schema"]
        Path(base.manifest_path).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        if request.engine.value == "godot4":
            self._write_godot(pack_dir / "godot4", polygons, animations, tilesets, asset_by_id)
        elif request.engine.value == "unity2d":
            self._write_unity(pack_dir / "unity2d", game_ready)

        self._rebuild_archive(pack_dir, Path(base.archive_path))
        return GameReadyPackExportResult(
            **base.model_dump(),
            animation_count=len(animations),
            tileset_count=len(tilesets),
            polygon_collision_count=len(polygons),
        )

    def _write_godot(self, root: Path, polygons, animations, tilesets, asset_by_id: dict) -> None:
        self._write_godot_polygons(root, polygons, asset_by_id)
        self._write_godot_animations(root, animations)
        self._write_godot_tilesets(root, tilesets)
        (root / "GAME_READY_2D.md").write_text(
            "Game-ready resources include CollisionPolygon2D prefab data, AnimatedSprite2D scenes, and TileSet builder scripts. Run each tileset builder in the Godot editor once to create its native .tres TileSet resource.\n",
            encoding="utf-8",
        )

    def _write_godot_polygons(self, root: Path, polygons: list[dict], asset_by_id: dict) -> None:
        prefab_dir = root / "prefabs"
        for polygon in polygons:
            asset_id = polygon["asset_id"]
            path = prefab_dir / f"{asset_id}.tscn"
            asset = asset_by_id.get(asset_id)
            if not path.is_file() or not asset:
                continue
            width = max(1, int(asset.get("width") or 1))
            height = max(1, int(asset.get("height") or 1))
            px = float(polygon["pivot_x"])
            py = float(polygon["pivot_y"])
            vectors = ", ".join(
                f"Vector2({(point['x'] - px) * width:.4f}, {(point['y'] - py) * height:.4f})"
                for point in polygon["points"]
            )
            body_type = "Area2D" if polygon["is_trigger"] else "StaticBody2D"
            text = path.read_text(encoding="utf-8")
            text += (
                "\n"
                f'[node name="CollisionBody" type="{body_type}" parent="."]\n\n'
                '[node name="CollisionPolygon2D" type="CollisionPolygon2D" parent="CollisionBody"]\n'
                f"polygon = PackedVector2Array({vectors})\n"
            )
            path.write_text(text, encoding="utf-8")

    @staticmethod
    def _write_godot_animations(root: Path, animations) -> None:
        animation_dir = root / "animations"
        animation_dir.mkdir(parents=True, exist_ok=True)
        for clip in animations:
            unique_ids = list(dict.fromkeys(clip.frame_asset_ids))
            resource_ids = {asset_id: index + 1 for index, asset_id in enumerate(unique_ids)}
            lines = [f"[gd_scene load_steps={len(unique_ids) + 2} format=3]", ""]
            for asset_id in unique_ids:
                lines.append(
                    f'[ext_resource type="Texture2D" path="res://godot4/assets/{asset_id}.png" id="{resource_ids[asset_id]}_tex"]'
                )
            frame_entries = ", ".join(
                '{"duration": 1.0, "texture": ExtResource("%d_tex")}' % resource_ids[asset_id]
                for asset_id in clip.frame_asset_ids
            )
            lines += [
                "",
                '[sub_resource type="SpriteFrames" id="SpriteFrames_main"]',
                "animations = [{",
                f'"frames": [{frame_entries}],',
                f'"loop": {str(clip.loop).lower()},',
                '"name": &"default",',
                f'"speed": {clip.fps:.6f}',
                "}]",
                "",
                f'[node name="{Asset2DGameReadyPackService._safe_name(clip.name)}" type="AnimatedSprite2D"]',
                'sprite_frames = SubResource("SpriteFrames_main")',
                'animation = &"default"',
                'autoplay = "default"',
            ]
            (animation_dir / f"{clip.id}.tscn").write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def _write_godot_tilesets(root: Path, tilesets) -> None:
        tileset_dir = root / "tilesets"
        tileset_dir.mkdir(parents=True, exist_ok=True)
        for tileset in tilesets:
            paths = ", ".join(f'"res://godot4/assets/{asset_id}.png"' for asset_id in tileset.tile_asset_ids)
            script = f'''@tool
extends EditorScript

func _run():
    var tile_set = TileSet.new()
    tile_set.tile_size = Vector2i({tileset.tile_width}, {tileset.tile_height})
    var texture_paths = [{paths}]
    for texture_path in texture_paths:
        var texture = load(texture_path)
        if texture == null:
            push_warning("Missing tile texture: " + texture_path)
            continue
        var source = TileSetAtlasSource.new()
        source.texture = texture
        source.texture_region_size = Vector2i({tileset.tile_width}, {tileset.tile_height})
        source.create_tile(Vector2i(0, 0))
        tile_set.add_source(source)
    var output = "res://godot4/tilesets/{tileset.id}.tres"
    ResourceSaver.save(tile_set, output)
    print("Game Creater TileSet saved: " + output)
'''
            (tileset_dir / f"build_{tileset.id}.gd").write_text(script, encoding="utf-8")
            (tileset_dir / f"{tileset.id}.json").write_text(
                json.dumps(tileset.model_dump(mode="json"), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    @staticmethod
    def _write_unity(root: Path, game_ready: dict) -> None:
        pack_root = root / "Assets" / "GameCreaterPack"
        pack_root.mkdir(parents=True, exist_ok=True)
        (pack_root / "game_ready_2d.json").write_text(
            json.dumps(game_ready, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        editor = pack_root / "Editor"
        editor.mkdir(parents=True, exist_ok=True)
        (editor / "GameCreaterGameReady2DBuilder.cs").write_text(
            r'''using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;
using UnityEngine.Tilemaps;

[Serializable] public class GCPoint { public float x; public float y; }
[Serializable] public class GCPolygon { public string asset_id; public GCPoint[] points; public bool is_trigger; }
[Serializable] public class GCAnimation { public string id; public string name; public string[] frame_asset_ids; public float fps; public bool loop; }
[Serializable] public class GCTileSet { public string id; public string name; public string[] tile_asset_ids; public int tile_width; public int tile_height; public string[] terrain_tags; }
[Serializable] public class GCGameReady { public string schema; public string pack_id; public GCPolygon[] collision_polygons; public GCAnimation[] animations; public GCTileSet[] tilesets; }

public static class GameCreaterGameReady2DBuilder
{
    [MenuItem("Game Creater/Build Game Ready 2D Resources")]
    public static void Build()
    {
        GameCreaterRuntimePrefabBuilder.Build();
        const string root = "Assets/GameCreaterPack";
        var doc = JsonUtility.FromJson<GCGameReady>(File.ReadAllText(Path.Combine(root, "game_ready_2d.json")));
        Directory.CreateDirectory(Path.Combine(root, "Animations"));
        Directory.CreateDirectory(Path.Combine(root, "Tiles"));
        ApplyPolygons(root, doc.collision_polygons ?? Array.Empty<GCPolygon>());
        BuildAnimations(root, doc.animations ?? Array.Empty<GCAnimation>());
        BuildTiles(root, doc.tilesets ?? Array.Empty<GCTileSet>());
        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();
        Debug.Log("Game Creater: built polygon colliders, animation clips and Tile assets.");
    }

    static void ApplyPolygons(string root, GCPolygon[] polygons)
    {
        foreach (var item in polygons)
        {
            var prefabPath = $"{root}/Prefabs/{item.asset_id}.prefab";
            var instance = PrefabUtility.LoadPrefabContents(prefabPath);
            if (instance == null) continue;
            var sprite = instance.GetComponent<SpriteRenderer>()?.sprite;
            if (sprite == null) { PrefabUtility.UnloadPrefabContents(instance); continue; }
            foreach (var old in instance.GetComponents<Collider2D>()) UnityEngine.Object.DestroyImmediate(old);
            var collider = instance.AddComponent<PolygonCollider2D>();
            collider.isTrigger = item.is_trigger;
            var width = sprite.rect.width;
            var height = sprite.rect.height;
            var pivot = sprite.pivot;
            var ppu = sprite.pixelsPerUnit;
            var points = item.points.Select(p => new Vector2((p.x * width - pivot.x) / ppu, (pivot.y - p.y * height) / ppu)).ToArray();
            collider.pathCount = 1;
            collider.SetPath(0, points);
            PrefabUtility.SaveAsPrefabAsset(instance, prefabPath);
            PrefabUtility.UnloadPrefabContents(instance);
        }
    }

    static void BuildAnimations(string root, GCAnimation[] animations)
    {
        foreach (var item in animations)
        {
            var clip = new AnimationClip { frameRate = item.fps, name = item.name };
            var keys = new ObjectReferenceKeyframe[item.frame_asset_ids.Length];
            for (var i = 0; i < item.frame_asset_ids.Length; i++)
            {
                keys[i] = new ObjectReferenceKeyframe {
                    time = i / item.fps,
                    value = AssetDatabase.LoadAssetAtPath<Sprite>($"{root}/assets/{item.frame_asset_ids[i]}.png")
                };
            }
            var binding = EditorCurveBinding.PPtrCurve("", typeof(SpriteRenderer), "m_Sprite");
            AnimationUtility.SetObjectReferenceCurve(clip, binding, keys);
            var settings = AnimationUtility.GetAnimationClipSettings(clip);
            settings.loopTime = item.loop;
            AnimationUtility.SetAnimationClipSettings(clip, settings);
            var path = $"{root}/Animations/{item.id}.anim";
            if (AssetDatabase.LoadAssetAtPath<AnimationClip>(path) != null) AssetDatabase.DeleteAsset(path);
            AssetDatabase.CreateAsset(clip, path);
        }
    }

    static void BuildTiles(string root, GCTileSet[] tilesets)
    {
        foreach (var set in tilesets)
        {
            var folder = $"{root}/Tiles/{set.id}";
            Directory.CreateDirectory(folder);
            foreach (var assetId in set.tile_asset_ids)
            {
                var sprite = AssetDatabase.LoadAssetAtPath<Sprite>($"{root}/assets/{assetId}.png");
                if (sprite == null) continue;
                var tile = ScriptableObject.CreateInstance<Tile>();
                tile.sprite = sprite;
                tile.colliderType = Tile.ColliderType.Sprite;
                var path = $"{folder}/{assetId}.asset";
                if (AssetDatabase.LoadAssetAtPath<Tile>(path) != null) AssetDatabase.DeleteAsset(path);
                AssetDatabase.CreateAsset(tile, path);
            }
        }
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
    def _safe_name(value: str) -> str:
        clean = re.sub(r"[^A-Za-z0-9_]", "_", value).strip("_")
        return clean or "GameReady2D"
