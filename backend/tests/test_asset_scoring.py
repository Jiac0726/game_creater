from __future__ import annotations

import numpy as np

from app.models import BBox
from app.services.asset_scoring import score_asset


def test_asset_score_is_bounded_and_reports_components() -> None:
    mask = np.zeros((100, 100), dtype=bool)
    mask[20:60, 20:60] = True

    score, components = score_asset(
        mask=mask,
        confidence=0.8,
        scene_width=100,
        scene_height=100,
        bbox=BBox(x1=20, y1=20, x2=60, y2=60),
    )

    assert 0.0 <= score <= 1.0
    assert set(components) == {"confidence", "size", "fill", "completeness", "area_ratio"}
    assert components["confidence"] == 0.8
    assert components["area_ratio"] == 0.16


def test_larger_interior_asset_scores_above_tiny_fragment_at_same_confidence() -> None:
    large = np.zeros((100, 100), dtype=bool)
    large[20:60, 20:60] = True
    tiny = np.zeros((100, 100), dtype=bool)
    tiny[40:43, 40:43] = True

    large_score, _ = score_asset(
        large,
        confidence=0.7,
        scene_width=100,
        scene_height=100,
        bbox=(20, 20, 60, 60),
    )
    tiny_score, _ = score_asset(
        tiny,
        confidence=0.7,
        scene_width=100,
        scene_height=100,
        bbox=(40, 40, 43, 43),
    )

    assert large_score > tiny_score


def test_lower_detector_confidence_reduces_score_for_same_geometry() -> None:
    mask = np.zeros((80, 80), dtype=bool)
    mask[10:40, 10:40] = True

    high, _ = score_asset(mask, 0.9, 80, 80, (10, 10, 40, 40))
    low, _ = score_asset(mask, 0.2, 80, 80, (10, 10, 40, 40))

    assert high > low


def test_semantic_value_contributes_to_score_without_becoming_a_hard_filter() -> None:
    mask = np.zeros((80, 80), dtype=bool)
    mask[10:40, 10:40] = True

    known, known_components = score_asset(
        mask,
        confidence=0.7,
        scene_width=80,
        scene_height=80,
        bbox=(10, 10, 40, 40),
        semantic_value=1.0,
    )
    unknown, unknown_components = score_asset(
        mask,
        confidence=0.7,
        scene_width=80,
        scene_height=80,
        bbox=(10, 10, 40, 40),
        semantic_value=0.45,
    )

    assert known > unknown
    assert unknown > 0
    assert known_components["semantic"] == 1.0
    assert unknown_components["semantic"] == 0.45
