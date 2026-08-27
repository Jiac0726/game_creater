from __future__ import annotations

import pytest

from app.services.detection_filter import (
    box_iou,
    deduplicate_detections,
    labels_equivalent,
)


def test_box_iou_handles_overlap_and_disjoint_boxes() -> None:
    assert box_iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert box_iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    assert 0.0 < box_iou((0, 0, 10, 10), (5, 5, 15, 15)) < 1.0


def test_same_label_high_iou_keeps_highest_confidence_only() -> None:
    boxes = [(10, 10, 60, 60), (12, 12, 61, 61), (70, 10, 95, 45)]
    scores = [0.91, 0.74, 0.80]
    labels = ["tree", "tree", "tree"]

    keep = deduplicate_detections(boxes, scores, labels, iou_threshold=0.65)

    assert keep == [0, 2]


def test_same_label_separate_instances_are_preserved() -> None:
    boxes = [(0, 0, 30, 30), (40, 0, 70, 30), (80, 0, 110, 30)]
    scores = [0.9, 0.85, 0.8]
    labels = ["tree", "tree", "tree"]

    keep = deduplicate_detections(boxes, scores, labels)

    assert keep == [0, 1, 2]


def test_similar_cross_label_boxes_require_strict_overlap_to_suppress() -> None:
    boxes = [(10, 10, 60, 60), (11, 11, 60, 60)]
    scores = [0.88, 0.72]
    labels = ["wooden crate", "crate"]

    assert labels_equivalent(labels[0], labels[1])
    keep = deduplicate_detections(
        boxes,
        scores,
        labels,
        iou_threshold=0.65,
        cross_label_iou_threshold=0.90,
    )

    assert keep == [0]


def test_nested_semantic_labels_survive_when_boxes_are_not_nearly_identical() -> None:
    boxes = [(0, 0, 100, 100), (20, 60, 60, 95)]
    scores = [0.9, 0.82]
    labels = ["tree", "tree stump"]

    keep = deduplicate_detections(
        boxes,
        scores,
        labels,
        cross_label_iou_threshold=0.92,
    )

    assert keep == [0, 1]


def test_mismatched_inputs_raise() -> None:
    with pytest.raises(ValueError, match="same length"):
        deduplicate_detections([(0, 0, 10, 10)], [0.9, 0.8], ["tree"])
