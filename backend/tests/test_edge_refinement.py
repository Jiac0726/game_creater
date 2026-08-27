from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from app.services.edge_refinement import EdgeRefinementService
from app.services.pipeline import AssetSplitPipeline


class FakeBiRefNetClient:
    def __init__(self) -> None:
        self.last_size: tuple[int, int] | None = None

    def health(self) -> dict:
        return {"ready": True, "loaded": True, "model_id": "fake-birefnet"}

    def predict_alpha(self, image: Image.Image) -> Image.Image:
        self.last_size = image.size
        width, height = image.size
        gradient = np.tile(np.linspace(20, 235, width, dtype=np.uint8), (height, 1))
        return Image.fromarray(gradient, mode="L")


def test_edge_refinement_preserves_binary_mask_and_bbox(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GAME_CREATER_MODE", "mock")
    source = tmp_path / "scene.png"
    Image.new("RGB", (120, 80), "white").save(source)
    workspace = tmp_path / "workspace"
    manifest = AssetSplitPipeline(workspace).run(source, ["tree"])
    asset = manifest.assets[0]
    scene_dir = workspace / manifest.scene_id

    mask_path = scene_dir / asset.mask
    image_path = scene_dir / asset.image
    mask_before = mask_path.read_bytes()
    bbox_before = asset.bbox.model_dump()
    original_alpha = np.asarray(Image.open(image_path).convert("RGBA").getchannel("A"))
    assert set(np.unique(original_alpha)).issubset({0, 255})

    fake = FakeBiRefNetClient()
    service = EdgeRefinementService(workspace, client=fake)
    refined = service.refine(manifest.scene_id, asset.id, radius=4)

    assert refined.bbox.model_dump() == bbox_before
    assert mask_path.read_bytes() == mask_before
    assert fake.last_size is not None
    assert fake.last_size[0] >= refined.bbox.x2 - refined.bbox.x1
    assert fake.last_size[1] >= refined.bbox.y2 - refined.bbox.y1

    refined_alpha = np.asarray(Image.open(image_path).convert("RGBA").getchannel("A"))
    unique = np.unique(refined_alpha)
    assert any(0 < int(value) < 255 for value in unique)
    assert refined_alpha.shape == original_alpha.shape


def test_edge_refiner_health_is_delegated(tmp_path: Path) -> None:
    fake = FakeBiRefNetClient()
    service = EdgeRefinementService(tmp_path, client=fake)

    assert service.health()["ready"] is True
