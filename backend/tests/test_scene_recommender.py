from __future__ import annotations

from app.models import AssetRecord, BBox, SceneManifest
from app.services.scene_recommender import SceneRecommender
from app.services.semantic_engine import SemanticEngine


def make_manifest(labels: list[str]) -> SceneManifest:
    assets = [
        AssetRecord(
            id=f"asset_{index:04d}",
            label=label,
            confidence=0.9,
            bbox=BBox(x1=0, y1=0, x2=10, y2=10),
            image=f"assets/{index}.png",
            mask=f"masks/{index}.png",
        )
        for index, label in enumerate(labels, start=1)
    ]
    return SceneManifest(
        scene_id="123456abcdef",
        source_image="scene.png",
        width=100,
        height=100,
        mode="mock",
        prompts=labels,
        assets=assets,
    )


def test_recommender_reports_coverage_and_missing_forest_assets() -> None:
    expansion = SemanticEngine().expand("森林", depth=1, max_per_group=30)
    manifest = make_manifest(["tree", "rock"])

    result = SceneRecommender().recommend(manifest, expansion, max_results=20)

    assert result.matched_concept_label == "森林"
    assert result.candidate_count > 2
    assert result.matched_count >= 2
    assert 0 < result.coverage_ratio < 1

    missing_en = {item.en for item in result.missing}
    assert "tree" not in missing_en
    assert "rock" not in missing_en
    assert "bush" in missing_en


def test_recommender_accepts_chinese_renamed_assets() -> None:
    expansion = SemanticEngine().expand("森林", depth=1, max_per_group=30)
    manifest = make_manifest(["树木"])

    result = SceneRecommender().recommend(manifest, expansion)

    missing_en = {item.en for item in result.missing}
    assert "tree" not in missing_en


def test_recommender_rejects_unmatched_concept() -> None:
    expansion = SemanticEngine().expand("不存在的概念xyz")
    manifest = make_manifest([])

    try:
        SceneRecommender().recommend(manifest, expansion)
    except ValueError as exc:
        assert "matched ontology concept" in str(exc)
    else:
        raise AssertionError("Expected ValueError for an unmatched concept")
