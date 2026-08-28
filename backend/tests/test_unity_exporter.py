from __future__ import annotations

import json
import zipfile
from pathlib import Path

from PIL import Image

from app.services.pipeline import AssetSplitPipeline
from app.services.unity_exporter import UnityExporter


def _scene(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GAME_CREATER_MODE", "mock")
    source = tmp_path / "scene.png"
    Image.new("RGB", (160, 90), "white").save(source)
    workspace = tmp_path / "workspace"
    manifest = AssetSplitPipeline(workspace).run(source, ["tree", "crate"])
    return workspace, manifest


def test_unity_export_contains_assets_layout_editor_builder_and_metadata(tmp_path: Path, monkeypatch) -> None:
    workspace, manifest = _scene(tmp_path, monkeypatch)
    archive_path = UnityExporter(workspace, tmp_path / "exports").export(manifest.scene_id)

    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        layout = json.loads(
            archive.read("Assets/GameCreater/Generated/layout.json").decode("utf-8")
        )
        builder = archive.read(
            "Assets/GameCreater/Editor/GameCreaterSceneBuilder.cs"
        ).decode("utf-8")
        metadata_script = archive.read(
            "Assets/GameCreater/Runtime/GameCreaterAssetMetadata.cs"
        ).decode("utf-8")

    assert "README_UNITY_IMPORT.txt" in names
    assert "Assets/GameCreater/Generated/layout.json" in names
    assert "Assets/GameCreater/Generated/scene.json" in names
    assert "Assets/GameCreater/Reference/source.png" in names
    assert {f"Assets/GameCreater/Textures/{asset.id}.png" for asset in manifest.assets}.issubset(names)

    assert layout["format"] == "game-creater-scene-layout"
    assert len(layout["assets"]) == len(manifest.assets)
    assert 'MenuItem("Tools/Game Creater/Build Generated 2D Scene")' in builder
    assert "EditorSceneManager.SaveScene(scene, ScenePath)" in builder
    assert "TextureImporterType.Sprite" in builder
    assert "spritePixelsPerUnit = PixelsPerUnit" in builder
    assert "renderer.sortingOrder" in builder
    assert "class GameCreaterAssetMetadata" in metadata_script


def test_unity_builder_converts_y_down_layout_into_y_up_world_coordinates(tmp_path: Path, monkeypatch) -> None:
    workspace, manifest = _scene(tmp_path, monkeypatch)
    archive_path = UnityExporter(workspace, tmp_path / "exports").export(manifest.scene_id)

    with zipfile.ZipFile(archive_path) as archive:
        builder = archive.read(
            "Assets/GameCreater/Editor/GameCreaterSceneBuilder.cs"
        ).decode("utf-8")

    assert "sourceCenterX = entry.anchor.position[0] + entry.texture_offset[0]" in builder
    assert "sourceCenterY = entry.anchor.position[1] + entry.texture_offset[1]" in builder
    assert "layout.source_size.height - sourceCenterY" in builder
    assert "100 source pixels = 1 Unity world unit" in archive.read(
        "README_UNITY_IMPORT.txt"
    ).decode("utf-8")
