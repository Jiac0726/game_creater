from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.services.grounded_sam2_local import GroundedSam2LocalAdapter


class FakePointPredictor:
    def __init__(self) -> None:
        self.last_call = None
        self.image = None

    def set_image(self, image) -> None:
        self.image = image

    def predict(self, *, point_coords, point_labels, box, multimask_output):
        self.last_call = {
            "point_coords": np.asarray(point_coords),
            "point_labels": np.asarray(point_labels),
            "box": None if box is None else np.asarray(box),
            "multimask_output": multimask_output,
        }
        height, width = self.image.shape[:2]
        masks = np.zeros((3, height, width), dtype=bool)
        masks[0, 5:20, 5:20] = True
        masks[1, 10:40, 12:46] = True
        masks[2, 2:12, 2:12] = True
        scores = np.asarray([0.25, 0.93, 0.51], dtype=np.float32)
        return masks, scores, None


def _adapter() -> tuple[GroundedSam2LocalAdapter, FakePointPredictor]:
    adapter = GroundedSam2LocalAdapter()
    predictor = FakePointPredictor()
    adapter._grounding_model = object()
    adapter._sam2_predictor = predictor
    adapter._load_image = lambda path: (np.zeros((64, 80, 3), dtype=np.uint8), object())
    adapter._device = "cpu"
    return adapter, predictor


def test_segment_points_uses_positive_negative_points_and_best_mask(tmp_path: Path) -> None:
    adapter, predictor = _adapter()

    mask, score = adapter.segment_points(
        tmp_path / "unused.png",
        [(20, 20), (60, 50)],
        [1, 0],
        box=(8, 8, 55, 50),
    )

    assert score == pytest.approx(0.93, abs=1e-5)
    assert mask.dtype == bool
    assert mask.shape == (64, 80)
    assert mask[15, 20]
    assert predictor.last_call is not None
    assert predictor.last_call["point_labels"].tolist() == [1, 0]
    assert predictor.last_call["box"].tolist() == [8.0, 8.0, 55.0, 50.0]
    assert predictor.last_call["multimask_output"] is True


def test_segment_points_requires_positive_point(tmp_path: Path) -> None:
    adapter, _ = _adapter()

    with pytest.raises(ValueError, match="positive"):
        adapter.segment_points(tmp_path / "unused.png", [(10, 10)], [0])


def test_segment_points_rejects_out_of_bounds_coordinates(tmp_path: Path) -> None:
    adapter, _ = _adapter()

    with pytest.raises(ValueError, match="x coordinate"):
        adapter.segment_points(tmp_path / "unused.png", [(999, 10)], [1])
