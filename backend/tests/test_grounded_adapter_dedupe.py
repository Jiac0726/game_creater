from __future__ import annotations

from pathlib import Path

import numpy as np

from app.services.grounded_sam2_local import GroundedSam2LocalAdapter


class FakeBoxes:
    shape = (3, 4)
    dtype = "fake"

    def numel(self) -> int:
        return 12

    def detach(self):
        return self

    def cpu(self):
        return self

    def __mul__(self, other):
        return self


class FakeScores:
    def detach(self):
        return self

    def cpu(self):
        return self

    def tolist(self):
        return [0.92, 0.71, 0.83]


class FakeConverted:
    def __init__(self, value: np.ndarray) -> None:
        self.value = value

    def numpy(self) -> np.ndarray:
        return self.value


class FakeTorch:
    @staticmethod
    def tensor(value, dtype=None):
        return value


class FakeSamPredictor:
    def __init__(self) -> None:
        self.boxes_seen: np.ndarray | None = None

    def set_image(self, image) -> None:
        self.image = image

    def predict(self, *, point_coords, point_labels, box, multimask_output):
        self.boxes_seen = np.asarray(box)
        height, width = self.image.shape[:2]
        masks = []
        for x1, y1, x2, y2 in self.boxes_seen.astype(int):
            mask = np.zeros((1, height, width), dtype=bool)
            mask[0, y1:y2, x1:x2] = True
            masks.append(mask)
        return np.asarray(masks), None, None


def test_adapter_dedupes_boxes_before_sam_and_reports_stats(tmp_path: Path) -> None:
    adapter = GroundedSam2LocalAdapter()
    adapter._torch = FakeTorch()
    adapter._load_image = lambda path: (np.zeros((100, 120, 3), dtype=np.uint8), object())
    adapter._predict = lambda **kwargs: (
        FakeBoxes(),
        FakeScores(),
        ["tree", "tree", "rock"],
    )
    adapter._box_convert = lambda **kwargs: FakeConverted(
        np.asarray(
            [
                [10, 10, 60, 70],
                [12, 11, 61, 70],
                [75, 15, 110, 55],
            ],
            dtype=np.float32,
        )
    )
    adapter._grounding_model = object()
    adapter._sam2_predictor = FakeSamPredictor()
    adapter._device = "cpu"

    detections, masks = adapter.predict(tmp_path / "unused.png", ["tree", "rock"])

    assert adapter._sam2_predictor.boxes_seen is not None
    assert adapter._sam2_predictor.boxes_seen.shape[0] == 2
    assert [item.label for item in detections] == ["tree", "rock"]
    assert len(masks) == 2
    assert adapter.last_stats == {
        "raw_detections": 3,
        "valid_detections": 3,
        "after_box_dedupe": 2,
        "after_mask_dedupe": 2,
        "box_duplicates_removed": 1,
        "mask_duplicates_removed": 0,
    }
