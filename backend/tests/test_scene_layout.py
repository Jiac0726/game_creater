from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.services.pipeline import AssetSplitPipeline
from app.services.scene_layout import SceneLayoutBuilder


def test_scene_layout_uses_bottom_center_anchor_and_source_pixels(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GAME_CREATER_MODE", "mock")
    source = tmp_path / "scene.png"
    Image.new("RGB", (100, 60), "white").save(source)
    manifest = AssetSplitPipeline(tmp_path / "workspace").run(source, ["tree", "rock"])

    layout = SceneLayoutBuilder().build(manifest)

    assert layout["format"] == "game-creater-scene-layout"
    assert layout["version"] == 1
    assert layout["source_size"] == {"width": 100, "height": 60}
    assert layout["coordinate_system"]["unit"] == "source_pixel"
    assert len(layout["assets"]) == 2

    for asset, entry in zip(manifest.assets, layout["assets"]):
        width = asset.bbox.x2 - asset.bbox.x1
        height = asset.bbox.y2 - asset.bbox.y1
        assert entry["id"] == asset.id
        assert entry["size"] == {"width": width, "height": height}
        assert entry["anchor"]["normalized"] == [0.5, 1.0]
        assert entry["anchor"]["position"] == [
            (asset.bbox.x1 + asset.bbox.x2) / 2.0,
            float(asset.bbox.y2),
        ]
        assert entry["texture_offset"] == [0.0, -height / 2.0]
        assert entry["sort_y"] == float(asset.bbox.y2)
