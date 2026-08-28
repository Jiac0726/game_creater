from __future__ import annotations

import json
import zipfile
from pathlib import Path

from app.models import AssetRecord, SceneManifest
from app.services.scene_layout import SceneLayoutBuilder
from app.services.scene_store import SceneStore


class UnityExporter:
    """Export a Unity Editor import bundle rather than hand-writing Unity YAML.

    The ZIP is extracted into an existing Unity project root. Unity imports the
    PNGs normally, then the included Editor script consumes layout.json and
    builds/saves a 2D scene using supported Editor APIs.
    """

    def __init__(self, workspace: str | Path, export_dir: str | Path) -> None:
        self.workspace = Path(workspace)
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.store = SceneStore(self.workspace)
        self.layout_builder = SceneLayoutBuilder()

    def export(self, scene_id: str) -> Path:
        manifest = self.store.load(scene_id)
        layout = self.layout_builder.build(manifest)
        scene_dir = self.workspace / scene_id
        archive_path = self.export_dir / f"game_creater_{scene_id}_unity2d.zip"

        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "Assets/GameCreater/Generated/layout.json",
                json.dumps(layout, ensure_ascii=False, indent=2),
            )
            archive.writestr(
                "Assets/GameCreater/Generated/scene.json",
                manifest.model_dump_json(indent=2),
            )
            archive.writestr(
                "Assets/GameCreater/Runtime/GameCreaterAssetMetadata.cs",
                self._metadata_script(),
            )
            archive.writestr(
                "Assets/GameCreater/Editor/GameCreaterSceneBuilder.cs",
                self._editor_script(),
            )
            archive.writestr("README_UNITY_IMPORT.txt", self._readme(manifest))

            for asset in manifest.assets:
                source_asset = scene_dir / asset.image
                if not source_asset.is_file():
                    raise ValueError(f"Asset image is missing for {asset.id}: {source_asset}")
                archive.write(source_asset, arcname=self._unity_asset_path(asset))

            if manifest.source_file:
                source_reference = scene_dir / manifest.source_file
                if source_reference.is_file():
                    suffix = source_reference.suffix.lower() or ".png"
                    archive.write(
                        source_reference,
                        arcname=f"Assets/GameCreater/Reference/source{suffix}",
                    )

        return archive_path

    @staticmethod
    def _unity_asset_path(asset: AssetRecord) -> str:
        return f"Assets/GameCreater/Textures/{asset.id}.png"

    @staticmethod
    def _metadata_script() -> str:
        return r'''using UnityEngine;

public sealed class GameCreaterAssetMetadata : MonoBehaviour
{
    public string assetId;
    public string label;
    public string category;
    public float confidence;
    public float assetScore;
}
'''

    @staticmethod
    def _editor_script() -> str:
        return r'''using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

public static class GameCreaterSceneBuilder
{
    private const string Root = "Assets/GameCreater";
    private const string LayoutPath = Root + "/Generated/layout.json";
    private const string ScenePath = Root + "/Generated/GeneratedScene.unity";
    private const float PixelsPerUnit = 100f;

    [Serializable]
    private sealed class Layout
    {
        public SourceSize source_size;
        public LayoutAsset[] assets;
    }

    [Serializable]
    private sealed class SourceSize
    {
        public int width;
        public int height;
    }

    [Serializable]
    private sealed class LayoutAsset
    {
        public string id;
        public string label;
        public string category;
        public Anchor anchor;
        public float[] texture_offset;
        public float sort_y;
        public float confidence;
        public float asset_score;
    }

    [Serializable]
    private sealed class Anchor
    {
        public float[] position;
    }

    [MenuItem("Tools/Game Creater/Build Generated 2D Scene")]
    public static void BuildScene()
    {
        if (!File.Exists(LayoutPath))
        {
            EditorUtility.DisplayDialog("Game Creater", "Missing " + LayoutPath, "OK");
            return;
        }

        var layout = JsonUtility.FromJson<Layout>(File.ReadAllText(LayoutPath));
        if (layout == null || layout.source_size == null || layout.assets == null)
        {
            EditorUtility.DisplayDialog("Game Creater", "layout.json could not be parsed.", "OK");
            return;
        }

        Directory.CreateDirectory(Root + "/Generated");
        AssetDatabase.Refresh();
        ConfigureTextures(layout);
        AssetDatabase.Refresh();

        var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        var root = new GameObject("GameCreaterScene");

        foreach (var entry in layout.assets)
        {
            if (entry == null || string.IsNullOrEmpty(entry.id) || entry.anchor == null ||
                entry.anchor.position == null || entry.anchor.position.Length < 2 ||
                entry.texture_offset == null || entry.texture_offset.Length < 2)
            {
                continue;
            }

            string texturePath = Root + "/Textures/" + entry.id + ".png";
            var sprite = AssetDatabase.LoadAssetAtPath<Sprite>(texturePath);
            if (sprite == null)
            {
                Debug.LogWarning("Game Creater: sprite not imported: " + texturePath);
                continue;
            }

            var go = new GameObject(SafeName(entry));
            go.transform.SetParent(root.transform, false);

            // Unity's default sprite pivot is centered. Convert the portable
            // bottom-center anchor + texture offset back to the cropped image
            // center, then flip source-image Y-down into Unity Y-up.
            float sourceCenterX = entry.anchor.position[0] + entry.texture_offset[0];
            float sourceCenterY = entry.anchor.position[1] + entry.texture_offset[1];
            float worldX = sourceCenterX / PixelsPerUnit;
            float worldY = (layout.source_size.height - sourceCenterY) / PixelsPerUnit;
            go.transform.position = new Vector3(worldX, worldY, 0f);

            var renderer = go.AddComponent<SpriteRenderer>();
            renderer.sprite = sprite;
            renderer.sortingOrder = Mathf.Clamp(Mathf.RoundToInt(entry.sort_y), -32768, 32767);

            var metadata = go.AddComponent<GameCreaterAssetMetadata>();
            metadata.assetId = entry.id;
            metadata.label = entry.label;
            metadata.category = entry.category;
            metadata.confidence = entry.confidence;
            metadata.assetScore = entry.asset_score;
        }

        CreateCamera(layout, root.transform);
        if (!EditorSceneManager.SaveScene(scene, ScenePath))
        {
            Debug.LogError("Game Creater: failed to save scene to " + ScenePath);
            return;
        }

        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();
        Selection.activeGameObject = root;
        Debug.Log("Game Creater: generated Unity scene at " + ScenePath);
    }

    private static void ConfigureTextures(Layout layout)
    {
        foreach (var entry in layout.assets)
        {
            if (entry == null || string.IsNullOrEmpty(entry.id)) continue;
            string path = Root + "/Textures/" + entry.id + ".png";
            var importer = AssetImporter.GetAtPath(path) as TextureImporter;
            if (importer == null) continue;

            bool dirty = importer.textureType != TextureImporterType.Sprite ||
                         importer.spriteImportMode != SpriteImportMode.Single ||
                         Math.Abs(importer.spritePixelsPerUnit - PixelsPerUnit) > 0.001f ||
                         importer.mipmapEnabled;

            importer.textureType = TextureImporterType.Sprite;
            importer.spriteImportMode = SpriteImportMode.Single;
            importer.spritePixelsPerUnit = PixelsPerUnit;
            importer.alphaIsTransparency = true;
            importer.mipmapEnabled = false;
            importer.wrapMode = TextureWrapMode.Clamp;
            if (dirty) importer.SaveAndReimport();
        }
    }

    private static void CreateCamera(Layout layout, Transform parent)
    {
        var cameraObject = new GameObject("Main Camera");
        cameraObject.transform.SetParent(parent, false);
        cameraObject.tag = "MainCamera";
        var camera = cameraObject.AddComponent<Camera>();
        camera.orthographic = true;
        camera.clearFlags = CameraClearFlags.SolidColor;
        camera.backgroundColor = Color.black;

        float width = Mathf.Max(1, layout.source_size.width) / PixelsPerUnit;
        float height = Mathf.Max(1, layout.source_size.height) / PixelsPerUnit;
        camera.transform.position = new Vector3(width * 0.5f, height * 0.5f, -10f);
        camera.orthographicSize = height * 0.5f;
    }

    private static string SafeName(LayoutAsset entry)
    {
        string label = string.IsNullOrWhiteSpace(entry.label) ? "Asset" : entry.label.Trim();
        foreach (char invalid in Path.GetInvalidFileNameChars())
            label = label.Replace(invalid, '_');
        return entry.id + "_" + label;
    }
}
'''

    @staticmethod
    def _readme(manifest: SceneManifest) -> str:
        return f"""Game Creater -> Unity 2D import bundle

Scene ID: {manifest.scene_id}
Source size: {manifest.width} x {manifest.height}
Assets: {len(manifest.assets)}

This is intentionally an import bundle instead of a hand-written Unity scene.
It avoids fabricated Unity GUID/.meta files and lets Unity import PNG assets using
its normal AssetDatabase pipeline.

Usage:
1. Close Unity or keep the target project backed up/version-controlled.
2. Extract this ZIP into the ROOT of an existing Unity project so the included
   Assets/GameCreater folder lands under that project's Assets directory.
3. Open/re-focus Unity and allow scripts/assets to compile/import.
4. Choose:
     Tools > Game Creater > Build Generated 2D Scene
5. The generated scene is saved to:
     Assets/GameCreater/Generated/GeneratedScene.unity

Placement:
- The bundle consumes Assets/GameCreater/Generated/layout.json.
- 100 source pixels = 1 Unity world unit.
- Source Y-down coordinates are converted to Unity Y-up.
- Cropped Sprite centers are reconstructed from the portable bottom-center anchor.
- SpriteRenderer.sortingOrder uses source bbox bottom Y as a first-pass 2D order.

The reference source image is included only for comparison and is not added to
the generated scene.

Not generated yet:
- colliders
- navigation
- gameplay scripts
- true depth/occlusion reconstruction
"""
