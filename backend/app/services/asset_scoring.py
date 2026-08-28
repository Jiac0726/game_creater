from __future__ import annotations

import math

import numpy as np

from app.models import BBox


def score_from_components(
    components: dict[str, float],
    semantic_value: float | None = None,
) -> tuple[float, dict[str, float]]:
    """Combine normalized score components into a bounded Asset Score."""

    normalized = dict(components)
    confidence_score = min(1.0, max(0.0, float(normalized.get("confidence", 0.0))))
    size_score = min(1.0, max(0.0, float(normalized.get("size", 0.0))))
    fill_score = min(1.0, max(0.0, float(normalized.get("fill", 0.0))))
    completeness_score = min(1.0, max(0.0, float(normalized.get("completeness", 0.0))))

    normalized["confidence"] = round(confidence_score, 4)
    normalized["size"] = round(size_score, 4)
    normalized["fill"] = round(fill_score, 4)
    normalized["completeness"] = round(completeness_score, 4)

    if semantic_value is None:
        score = (
            0.45 * confidence_score
            + 0.25 * size_score
            + 0.15 * fill_score
            + 0.15 * completeness_score
        )
        normalized.pop("semantic", None)
    else:
        semantic_score = min(1.0, max(0.0, float(semantic_value)))
        normalized["semantic"] = round(semantic_score, 4)
        score = (
            0.35 * confidence_score
            + 0.20 * size_score
            + 0.12 * fill_score
            + 0.13 * completeness_score
            + 0.20 * semantic_score
        )

    return round(min(1.0, max(0.0, score)), 4), normalized


def score_asset(
    mask: np.ndarray,
    confidence: float,
    scene_width: int,
    scene_height: int,
    bbox: BBox | tuple[int, int, int, int],
    semantic_value: float | None = None,
) -> tuple[float, dict[str, float]]:
    """Return a bounded game-asset usefulness score.

    With no semantic value supplied this preserves the geometry/confidence v0
    weighting. When ontology evidence is available, semantic value contributes
    20% without becoming a hard filter.
    """

    normalized = np.asarray(mask, dtype=bool)
    scene_pixels = max(1, int(scene_width) * int(scene_height))
    mask_pixels = int(normalized.sum())
    area_ratio = mask_pixels / scene_pixels

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

    components = {
        "confidence": round(confidence_score, 4),
        "size": round(size_score, 4),
        "fill": round(fill_score, 4),
        "completeness": round(completeness_score, 4),
        "area_ratio": round(area_ratio, 6),
    }
    return score_from_components(components, semantic_value=semantic_value)
