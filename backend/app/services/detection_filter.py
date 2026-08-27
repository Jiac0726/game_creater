from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Sequence


Box = tuple[int, int, int, int]


def box_iou(a: Box, b: Box) -> float:
    """Return intersection-over-union for two xyxy boxes."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0, ix2 - ix1)
    ih = max(0, iy2 - iy1)
    intersection = iw * ih
    if intersection <= 0:
        return 0.0

    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


def normalize_label(label: str) -> str:
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", label.lower()).strip()
    return " ".join(value.split())


def labels_equivalent(a: str, b: str) -> bool:
    """Conservative label equivalence for duplicate suppression.

    Exact normalized labels are equivalent. Very similar labels or noun phrases
    that contain one another are treated as equivalent only when the boxes also
    overlap at the stricter cross-label threshold in ``deduplicate_detections``.
    """
    left = normalize_label(a)
    right = normalize_label(b)
    if not left or not right:
        return False
    if left == right:
        return True

    # Avoid collapsing short unrelated labels merely because one token matches.
    if min(len(left), len(right)) >= 4 and (left in right or right in left):
        return True
    return SequenceMatcher(None, left, right).ratio() >= 0.88


def deduplicate_detections(
    boxes: Sequence[Box],
    scores: Sequence[float],
    labels: Sequence[str],
    *,
    iou_threshold: float = 0.65,
    cross_label_iou_threshold: float = 0.92,
) -> list[int]:
    """Return indices to keep after confidence-first duplicate suppression.

    Same-label boxes use the normal IoU threshold. Similar-but-not-identical
    labels are only suppressed when their boxes are almost identical, which
    preserves legitimate nested assets such as ``tree`` and ``tree stump``.
    """
    if not (len(boxes) == len(scores) == len(labels)):
        raise ValueError("boxes, scores and labels must have the same length")

    iou_threshold = min(1.0, max(0.0, float(iou_threshold)))
    cross_label_iou_threshold = min(1.0, max(iou_threshold, float(cross_label_iou_threshold)))

    order = sorted(range(len(boxes)), key=lambda index: (-float(scores[index]), index))
    kept: list[int] = []

    for candidate in order:
        candidate_label = normalize_label(labels[candidate])
        duplicate = False
        for accepted in kept:
            overlap = box_iou(boxes[candidate], boxes[accepted])
            accepted_label = normalize_label(labels[accepted])

            if candidate_label == accepted_label:
                if overlap >= iou_threshold:
                    duplicate = True
                    break
            elif labels_equivalent(candidate_label, accepted_label):
                if overlap >= cross_label_iou_threshold:
                    duplicate = True
                    break

        if not duplicate:
            kept.append(candidate)

    # Stable spatial/model order is more convenient downstream than score order.
    return sorted(kept)
