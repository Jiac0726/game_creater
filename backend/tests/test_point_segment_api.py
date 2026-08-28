from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from app.models import AssetPointSegmentRequest, PointPrompt
from app.services.asset_editor import AssetEditor
from app.services.pipeline import AssetSplitPipeline
from app.services.scene_store import SceneStore


class FakePointAdapter:
    def segment_points(self, image_path, points, point_labels, *, box=None):
        mask = np.zeros((80, 120), dtype=bool)
        mask[18:52, 68:108] = True
        return mask, 0.88


def test_point_segment_api_creates_asset_from_sam_mask(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GAME_CREATER_MODE", "mock")
    source = tmp_path / "scene.png"
    Image.new("RGB", (120, 80), "white").save(source)
    workspace = tmp_path / "workspace"
    manifest = AssetSplitPipeline(workspace).run(source, ["tree"])

    import app.main as main

    fake_pipeline = AssetSplitPipeline(workspace)
    fake_pipeline.mode = "grounded_sam2_local"
    monkeypatch.setattr(fake_pipeline, "_get_grounded_adapter", lambda: FakePointAdapter())
    monkeypatch.setattr(main, "WORKSPACE", workspace)
    monkeypatch.setattr(main, "pipeline", fake_pipeline)
    monkeypatch.setattr(main, "scene_store", SceneStore(workspace))
    monkeypatch.setattr(main, "asset_editor", AssetEditor(workspace))

    result = main.point_segment_asset(
        manifest.scene_id,
        AssetPointSegmentRequest(
            points=[PointPrompt(x=80, y=30, positive=True)],
            label="wooden crate",
            category="prop",
        ),
    )

    assert len(result.assets) == 2
    added = result.assets[-1]
    assert added.label == "wooden crate"
    assert added.category == "prop"
    assert added.confidence == 0.88
    assert added.bbox.x1 == 68
    assert added.bbox.y1 == 18
    assert (workspace / manifest.scene_id / added.image).is_file()
    assert (workspace / manifest.scene_id / added.mask).is_file()
