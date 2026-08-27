from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.models import AssetMergeRequest, AssetSplitRequest, BBox
from app.services.asset_editor import AssetEditor
from app.services.pipeline import AssetSplitPipeline


def _scene(tmp_path: Path, monkeypatch, prompts: list[str]):
    monkeypatch.setenv("GAME_CREATER_MODE", "mock")
    source = tmp_path / "scene.png"
    Image.new("RGB", (120, 80), "white").save(source)
    workspace = tmp_path / "workspace"
    manifest = AssetSplitPipeline(workspace).run(source, prompts)
    return workspace, manifest


def test_delete_asset_removes_record_files_and_rebuilds_overlay(tmp_path: Path, monkeypatch) -> None:
    workspace, manifest = _scene(tmp_path, monkeypatch, ["tree", "rock"])
    editor = AssetEditor(workspace)
    removed = manifest.assets[0]
    scene_dir = workspace / manifest.scene_id

    result = editor.delete(manifest.scene_id, removed.id)

    assert [asset.label for asset in result.assets] == ["rock"]
    assert not (scene_dir / removed.image).exists()
    assert not (scene_dir / removed.mask).exists()
    assert (scene_dir / result.preview_image).is_file()


def test_merge_assets_replaces_sources_and_writes_union_asset(tmp_path: Path, monkeypatch) -> None:
    workspace, manifest = _scene(tmp_path, monkeypatch, ["tree", "rock"])
    editor = AssetEditor(workspace)
    source_paths = [
        workspace / manifest.scene_id / rel
        for asset in manifest.assets
        for rel in (asset.image, asset.mask)
    ]

    result = editor.merge(
        manifest.scene_id,
        AssetMergeRequest(
            asset_ids=[manifest.assets[0].id, manifest.assets[1].id],
            label="forest_cluster",
            category="environment",
        ),
    )

    assert len(result.assets) == 1
    merged = result.assets[0]
    assert merged.label == "forest_cluster"
    assert merged.category == "environment"
    assert merged.bbox.x1 <= manifest.assets[0].bbox.x1
    assert merged.bbox.x2 >= manifest.assets[1].bbox.x2
    assert (workspace / manifest.scene_id / merged.image).is_file()
    assert (workspace / manifest.scene_id / merged.mask).is_file()
    assert all(not path.exists() for path in source_paths)


def test_split_asset_by_rectangle_creates_two_unique_parts(tmp_path: Path, monkeypatch) -> None:
    workspace, manifest = _scene(tmp_path, monkeypatch, ["tree"])
    editor = AssetEditor(workspace)
    original = manifest.assets[0]
    mid_y = (original.bbox.y1 + original.bbox.y2) // 2

    result = editor.split(
        manifest.scene_id,
        original.id,
        AssetSplitRequest(
            rect=BBox(
                x1=original.bbox.x1,
                y1=original.bbox.y1,
                x2=original.bbox.x2,
                y2=mid_y,
            ),
            inside_label="tree_top",
            outside_label="tree_bottom",
        ),
    )

    assert len(result.assets) == 2
    assert {asset.label for asset in result.assets} == {"tree_top", "tree_bottom"}
    assert len({asset.id for asset in result.assets}) == 2
    assert all((workspace / manifest.scene_id / asset.image).is_file() for asset in result.assets)
    assert all((workspace / manifest.scene_id / asset.mask).is_file() for asset in result.assets)
    assert not (workspace / manifest.scene_id / original.image).exists()
    assert not (workspace / manifest.scene_id / original.mask).exists()


def test_pipeline_retains_source_image_for_later_edits(tmp_path: Path, monkeypatch) -> None:
    workspace, manifest = _scene(tmp_path, monkeypatch, ["tree"])

    assert manifest.source_file is not None
    assert (workspace / manifest.scene_id / manifest.source_file).is_file()
