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
            "schema": "game-creater/game-ready-2d/v2",
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
            "Game-ready resources include CollisionPolygon2D prefab data, AnimatedSprite2D scenes, and TileSet builder scripts with optional Godot 4 terrain metadata. Run each tileset builder in the Godot editor once to create its native .tres TileSet resource.\n",
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
            flat_values: list[str] = []
            for point in polygon["points"]:
                flat_values.append(f"{(point['x'] - px) * width:.4f}")
                flat_values.append(f"{(point['y'] - py) * height:.4f}")
            packed = ", ".join(flat_values)
            body_type = "Area2D" if polygon["is_trigger"] else "StaticBody2D"
            text = path.read_text(encoding="utf-8")
            text += (
                "\n"
                f'[node name="CollisionBody" type="{body_type}" parent="."]\n\n'
                '[node name="CollisionPolygon2D" type="CollisionPolygon2D" parent="CollisionBody"]\n'
                f"polygon = PackedVector2Array({packed})\n"
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
                f'"loop": {1 if clip.loop else 0},',
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
            entries = [
                {"asset_id": asset_id, "path": f"res://godot4/assets/{asset_id}.png"}
                for asset_id in tileset.tile_asset_ids
            ]
            rules = [rule.model_dump(mode="json") for rule in tileset.terrain_rules]
            terrain_names = list(dict.fromkeys(rule["terrain"] for rule in rules))
            mode_constant = (
                "TileSet.TERRAIN_MODE_MATCH_SIDES"
                if tileset.autotile_mode.value == "cardinal4"
                else "TileSet.TERRAIN_MODE_MATCH_CORNERS_AND_SIDES"
            )
            script = f'''@tool
extends EditorScript

const N = 1
const NE = 2
const E = 4
const SE = 8
const S = 16
const SW = 32
const W = 64
const NW = 128

func _apply_peering_bits(data: TileData, mask: int, terrain_id: int):
    if mask & N: data.set_terrain_peering_bit(TileSet.CELL_NEIGHBOR_TOP_SIDE, terrain_id)
    if mask & NE: data.set_terrain_peering_bit(TileSet.CELL_NEIGHBOR_TOP_RIGHT_CORNER, terrain_id)
    if mask & E: data.set_terrain_peering_bit(TileSet.CELL_NEIGHBOR_RIGHT_SIDE, terrain_id)
    if mask & SE: data.set_terrain_peering_bit(TileSet.CELL_NEIGHBOR_BOTTOM_RIGHT_CORNER, terrain_id)
    if mask & S: data.set_terrain_peering_bit(TileSet.CELL_NEIGHBOR_BOTTOM_SIDE, terrain_id)
    if mask & SW: data.set_terrain_peering_bit(TileSet.CELL_NEIGHBOR_BOTTOM_LEFT_CORNER, terrain_id)
    if mask & W: data.set_terrain_peering_bit(TileSet.CELL_NEIGHBOR_LEFT_SIDE, terrain_id)
    if mask & NW: data.set_terrain_peering_bit(TileSet.CELL_NEIGHBOR_TOP_LEFT_CORNER, terrain_id)

func _run():
    var tile_set = TileSet.new()
    tile_set.tile_size = Vector2i({tileset.tile_width}, {tileset.tile_height})
    var tile_entries = {json.dumps(entries, ensure_ascii=False)}
    var terrain_rules = {json.dumps(rules, ensure_ascii=False)}
    var terrain_names = {json.dumps(terrain_names, ensure_ascii=False)}
    var source_by_asset = {{}}

    if terrain_rules.size() > 0:
        tile_set.add_terrain_set()
        tile_set.set_terrain_set_mode(0, {mode_constant})
        for terrain_name in terrain_names:
            var terrain_id = tile_set.get_terrains_count(0)
            tile_set.add_terrain(0)
            tile_set.set_terrain_name(0, terrain_id, terrain_name)

    for entry in tile_entries:
        var texture = load(entry["path"])
        if texture == null:
            push_warning("Missing tile texture: " + entry["path"])
            continue
        var source = TileSetAtlasSource.new()
        source.texture = texture
        source.texture_region_size = Vector2i({tileset.tile_width}, {tileset.tile_height})
        source.create_tile(Vector2i(0, 0))
        tile_set.add_source(source)
        source_by_asset[entry["asset_id"]] = source

    for rule in terrain_rules:
        var source: TileSetAtlasSource = source_by_asset.get(rule["asset_id"])
        if source == null:
            continue
        var terrain_id = terrain_names.find(rule["terrain"])
        if terrain_id < 0:
            continue
        var data: TileData = source.get_tile_data(Vector2i(0, 0), 0)
        data.terrain_set = 0
        data.terrain = terrain_id
        _apply_peering_bits(data, int(rule["neighbor_mask"]), terrain_id)

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
        runtime_dir = pack_root / "Runtime"
        editor = pack_root / "Editor"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        editor.mkdir(parents=True, exist_ok=True)
        (runtime_dir / "GameCreaterAutoTile.cs").write_text(
            r'''using System;
using UnityEngine;
using UnityEngine.Tilemaps;

[Serializable]
public class GameCreaterAutoTileRule
{
    public int neighborMask;
    public int priority;
    public Sprite sprite;
}

public class GameCreaterAutoTile : TileBase
{
    public string terrain;
    public bool eightWay;
    public GameCreaterAutoTileRule[] rules = Array.Empty<GameCreaterAutoTileRule>();

    static readonly Vector3Int[] Directions = {
        new Vector3Int(0, 1, 0), new Vector3Int(1, 1, 0), new Vector3Int(1, 0, 0), new Vector3Int(1, -1, 0),
        new Vector3Int(0, -1, 0), new Vector3Int(-1, -1, 0), new Vector3Int(-1, 0, 0), new Vector3Int(-1, 1, 0)
    };

    public override void RefreshTile(Vector3Int position, ITilemap tilemap)
    {
        base.RefreshTile(position, tilemap);
        for (var i = 0; i < Directions.Length; i++)
        {
            if (!eightWay && (i % 2 == 1)) continue;
            tilemap.RefreshTile(position + Directions[i]);
        }
    }

    public override void GetTileData(Vector3Int position, ITilemap tilemap, ref TileData tileData)
    {
        var mask = 0;
        for (var i = 0; i < Directions.Length; i++)
        {
            if (!eightWay && (i % 2 == 1)) continue;
            var other = tilemap.GetTile(position + Directions[i]) as GameCreaterAutoTile;
            if (other != null && other.terrain == terrain) mask |= 1 << i;
        }
        GameCreaterAutoTileRule selected = null;
        foreach (var rule in rules)
        {
            if (rule.neighborMask != mask) continue;
            if (selected == null || rule.priority > selected.priority) selected = rule;
        }
        if (selected == null && rules.Length > 0) selected = rules[0];
        tileData.sprite = selected != null ? selected.sprite : null;
        tileData.colliderType = Tile.ColliderType.Sprite;
        tileData.flags = TileFlags.LockTransform;
        tileData.transform = Matrix4x4.identity;
        tileData.color = Color.white;
    }
}
''',
            encoding="utf-8",
        )
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
[Serializable] public class GCTerrainRule { public string asset_id; public string terrain; public int neighbor_mask; public int priority; }
[Serializable] public class GCTileSet { public string id; public string name; public string[] tile_asset_ids; public int tile_width; public int tile_height; public string[] terrain_tags; public string autotile_mode; public GCTerrainRule[] terrain_rules; }
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
        Debug.Log("Game Creater: built polygon colliders, animation clips, Tiles and AutoTiles.");
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

            var rules = set.terrain_rules ?? Array.Empty<GCTerrainRule>();
            if (set.autotile_mode == "none" || rules.Length == 0) continue;
            foreach (var terrainGroup in rules.GroupBy(rule => rule.terrain))
            {
                var autoTile = ScriptableObject.CreateInstance<GameCreaterAutoTile>();
                autoTile.terrain = terrainGroup.Key;
                autoTile.eightWay = set.autotile_mode == "eight8";
                autoTile.rules = terrainGroup
                    .OrderByDescending(rule => rule.priority)
                    .Select(rule => new GameCreaterAutoTileRule {
                        neighborMask = rule.neighbor_mask,
                        priority = rule.priority,
                        sprite = AssetDatabase.LoadAssetAtPath<Sprite>($"{root}/assets/{rule.asset_id}.png")
                    })
                    .Where(rule => rule.sprite != null)
                    .ToArray();
                var safeTerrain = string.Concat(terrainGroup.Key.Select(ch => char.IsLetterOrDigit(ch) ? ch : '_'));
                var path = $"{folder}/Auto_{safeTerrain}.asset";
                if (AssetDatabase.LoadAssetAtPath<GameCreaterAutoTile>(path) != null) AssetDatabase.DeleteAsset(path);
                AssetDatabase.CreateAsset(autoTile, path);
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
