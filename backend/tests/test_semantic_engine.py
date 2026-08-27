from __future__ import annotations

from app.services.semantic_engine import SemanticEngine


def test_semantic_engine_expands_abandoned_subway_station() -> None:
    engine = SemanticEngine()

    result = engine.expand("废弃地铁站", depth=2, max_per_group=12)

    assert result.matched_concept == "subway_station"
    assert result.matched_concept_label == "地铁站"
    assert "废弃" in result.modifiers
    assert result.groups
    assert result.detection_prompts
    assert "subway platform" in result.detection_prompts
    assert "ticket gate" in result.detection_prompts

    all_items = [item for group in result.groups for item in group.items]
    assert any(item.source.startswith("variant:") for item in all_items)


def test_semantic_engine_expands_magic_forest() -> None:
    engine = SemanticEngine()

    result = engine.expand("魔法森林", depth=2, max_per_group=20)

    assert result.matched_concept == "forest"
    assert "魔法" in result.modifiers
    assert "tree" in result.detection_prompts
    assert "mushroom" in result.detection_prompts
    assert len(result.detection_prompts) <= 40


def test_semantic_engine_unknown_keyword_returns_warning() -> None:
    engine = SemanticEngine()

    result = engine.expand("完全不存在于本体的随机概念xyz")

    assert result.matched_concept is None
    assert result.groups == []
    assert result.detection_prompts == []
    assert result.warnings


def test_semantic_engine_clamps_depth_and_group_size() -> None:
    engine = SemanticEngine()

    result = engine.expand("森林", depth=99, max_per_group=1)

    assert result.groups
    assert all(len(group.items) <= 1 for group in result.groups)


def test_semantic_catalog_exposes_concepts_and_modifiers() -> None:
    catalog = SemanticEngine().catalog()

    concept_keys = {item["key"] for item in catalog["concepts"]}
    modifier_keys = {item["key"] for item in catalog["modifiers"]}

    assert "forest" in concept_keys
    assert "subway_station" in concept_keys
    assert "abandoned" in modifier_keys
    assert catalog["groups"]["props"] == "道具"
