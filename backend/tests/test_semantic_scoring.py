from __future__ import annotations

from app.services.semantic_scoring import SemanticAssetScorer, semantic_asset_value


def test_known_asset_terms_receive_high_semantic_value() -> None:
    scorer = SemanticAssetScorer()

    assert scorer.score("tree") == 1.0
    assert scorer.score("ticket gate") == 1.0
    assert scorer.score("木箱") == 1.0


def test_modified_known_asset_label_still_scores_well() -> None:
    scorer = SemanticAssetScorer()

    assert scorer.score("ancient_tree_part_a") >= 0.8
    assert scorer.score("rusty ticket gate") >= 0.8


def test_unknown_asset_keeps_neutral_floor() -> None:
    scorer = SemanticAssetScorer()

    assert scorer.score("totally_unknown_visual_fragment_xyz") == 0.45


def test_cached_default_semantic_value_is_bounded() -> None:
    value = semantic_asset_value("barrel")

    assert 0.0 <= value <= 1.0
