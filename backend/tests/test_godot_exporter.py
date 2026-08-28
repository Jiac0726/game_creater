from __future__ import annotations

import json
import zipfile
from pathlib import Path

from PIL import Image

from app.services.godot_exporter import GodotExporter
from app.services.pipeline import AssetSplitPipeline


def _scene(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GAME_CREATER_MODE", "mock")
    source = tmp_path / "scene.png"
    Image.new("RGB", (120, 80), "white").save(source)
    workspace = tmp_path / "workspace"
    manifest = AssetSplitPipeline(workspace).run(source, ["tree", "wooden crate"])
    return workspace, manifest


def test_godot_export_contains_openable_project_scene_assets_and_metadata(tmp_path: Path, monkeypatch) -> None:
    workspace, manifest = _scene(tmp_path, monkeypatch)
    exporter = GodotExporter(workspace, tmp_path / "exports")

    archive_path = exporter.export(manifest.scene_id)

    assert archive_path.is_file()
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        project = archive.read("project.godot").decode("utf-8")
        scene = archive.read("scenes/generated_scene.tscn").decode("utf-8")
        metadata = json.loads(archive.read("metadata/scene.json").decode("utf-8"))

    assert "project.godot" in names
    assert "scenes/generated_scene.tscn" in names
    assert "metadata/scene.json" in names
    assert "README_GAME_CREATER.txt" in names
    assert "reference/source.png" in names
    assert {f"assets/{asset.id}.png" for asset in manifest.assets}.issubset(names)

    assert 'run/main_scene="res://scenes/generated_scene.tscn"' in project
    assert f"window/size/viewport_width={manifest.width}" in project
    assert f"window/size/viewport_height={manifest.height}" in project
    assert "[gd_scene format=3]" in scene
    assert '[node name="GeneratedScene" type="Node2D"]' in scene
    assert "y_sort_enabled = true" in scene
    assert scene.count('type="Sprite2D"') == len(manifest.assets)

    assert metadata["engine_export"]["engine"] == "godot"
    assert metadata["engine_export"]["sprite_anchor"] == "bbox bottom-center"
    assert len(metadata["assets"]) == len(manifest.assets)


def test_godot_sprite_positions_use_bbox_bottom_center_and_texture_offset(tmp_path: Path, monkeypatch) -> None:
    workspace, manifest = _scene(tmp_path, monkeypatch)
    exporter = GodotExporter(workspace, tmp_path / "exports")
    archive_path = exporter.export(manifest.scene_id)

    with zipfile.ZipFile(archive_path) as archive:
        scene = archive.read("scenes/generated_scene.tscn").decode("utf-8")

    for asset in manifest.assets:
        center_x = (asset.bbox.x1 + asset.bbox.x2) / 2.0
        bottom_y = float(asset.bbox.y2)
        height = asset.bbox.y2 - asset.bbox.y1
        assert (
            f"position = Vector2({exporter._number(center_x)}, {exporter._number(bottom_y)})"
            in scene
        )
        assert f"offset = Vector2(0, {exporter._number(-height / 2.0)})" in scene


def test_godot_export_does_not_instantiate_reference_source_image(tmp_path: Path, monkeypatch) -> None:
    workspace, manifest = _scene(tmp_path, monkeypatch)
    archive_path = GodotExporter(workspace, tmp_path / "exports").export(manifest.scene_id)

    with zipfile.ZipFile(archive_path) as archive:
        scene = archive.read("scenes/generated_scene.tscn").decode("utf-8")

    assert "reference/source" not in scene


def test_godot_export_api_returns_generated_zip(tmp_path: Path, monkeypatch) -> None:
    workspace, manifest = _scene(tmp_path, monkeypatch)
    exports = tmp_path / "api_exports"

    import app.main as main

    monkeypatch.setattr(main, "WORKSPACE", workspace)
    monkeypatch.setattr(main, "EXPORTS", exports)
    monkeypatch.setattr(main, "godot_exporter", GodotExporter(workspace, exports))

    response = main.export_scene_godot(manifest.scene_id)
    archive_path = Path(response.path)

    assert archive_path.is_file()
    assert response.media_type == "application/zip"
    with zipfile.ZipFile(archive_path) as archive:
        assert "project.godot" in archive.namelist()
        assert "scenes/generated_scene.tscn" in archive.namelist()
