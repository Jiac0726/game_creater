from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from app.services.pipeline import AssetSplitPipeline


def test_mock_pipeline_exports_assets_masks_and_manifest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GAME_CREATER_MODE", "mock")

    source = tmp_path / "scene.png"
    Image.new("RGB", (96, 64), "white").save(source)

    workspace = tmp_path / "workspace"
    pipeline = AssetSplitPipeline(workspace)
    manifest = pipeline.run(source, ["tree", "rock"])

    assert manifest.mode == "mock"
    assert manifest.width == 96
    assert manifest.height == 64
    assert len(manifest.assets) == 2

    scene_dir = workspace / manifest.scene_id
    manifest_path = scene_dir / "scene.json"
    assert manifest_path.is_file()

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["scene_id"] == manifest.scene_id
    assert [item["label"] for item in payload["assets"]] == ["tree", "rock"]

    for asset in manifest.assets:
        asset_path = scene_dir / asset.image
        mask_path = scene_dir / asset.mask
        assert asset_path.is_file()
        assert mask_path.is_file()

        rgba = Image.open(asset_path)
        mask = Image.open(mask_path)
        assert rgba.mode == "RGBA"
        assert mask.mode == "L"
        assert rgba.size == mask.size
        assert rgba.getchannel("A").getbbox() is not None


def test_mock_pipeline_uses_default_prompt(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GAME_CREATER_MODE", "mock")

    source = tmp_path / "scene.png"
    Image.new("RGB", (32, 32), "black").save(source)

    manifest = AssetSplitPipeline(tmp_path / "workspace").run(source, [])

    assert manifest.prompts == ["asset"]
    assert len(manifest.assets) == 1
    assert manifest.assets[0].label == "asset"
