from __future__ import annotations

import math

import numpy as np

from app.models import BBox


def score_asset(
    mask: np.ndarray,
    confidence: float,
    scene_width: int,
    scene_height: int,
    bbox: BBox | tuple[int, int, int, int],
) -> tuple[float, dict[str, float]]:
    """Return a conservative v0 game-asset usefulness score.

    This score intentionally uses only model-independent geometry plus detector
    confidence. It does not try to decide semantic game value yet; that will be
    added later by the Game Asset Ontology / semantic layer.
    """

    normalized = np.asarray(mask, dtype=bool)
    scene_pixels = max(1, int(scene_width) * int(scene_height))
    mask_pixels = int(normalized.sum())
    area_ratio = mask_pixels / scene_pixels

    # Roughly 3% of the scene is already large enough to receive full size credit.
    size_score = min(1.0, math.sqrt(max(0.0, area_ratio) / 0.03)) if area_ratio else 0.0

    if isinstance(bbox, BBox):
        x1, y1, x2, y2 = bbox.x1, bbox.y1, bbox.x2, bbox.y2
    else:
        x1, y1, x2, y2 = bbox

    bbox_pixels = max(1, max(0, x2 - x1) * max(0, y2 - y1))
    fill_ratio = min(1.0, mask_pixels / bbox_pixels)
    fill_score = min(1.0, fill_ratio / 0.60)

    touches = sum(
        (
            x1 <= 0,
            y1 <= 0,
            x2 >= scene_width,
            y2 >= scene_height,
        )
    )
    completeness_score = max(0.25, 1.0 - 0.20 * touches)
    confidence_score = min(1.0, max(0.0, float(confidence)))

    score = (
        0.45 * confidence_score
        + 0.25 * size_score
        + 0.15 * fill_score
        + 0.15 * completeness_score
    )
    score = min(1.0, max(0.0, score))

    components = {
        "confidence": round(confidence_score, 4),
        "size": round(size_score, 4),
        "fill": round(fill_score, 4),
        "completeness": round(completeness_score, 4),
        "area_ratio": round(area_ratio, 6),
    }
    return round(score, 4), components
