from __future__ import annotations

from difflib import SequenceMatcher
from functools import lru_cache

from app.services.semantic_engine import SemanticEngine


CATEGORY_MAP = {
    "buildings": "building",
    "structures": "structure",
    "props": "prop",
    "vegetation": "vegetation",
    "terrain": "terrain",
    "vehicles": "vehicle",
    "creatures": "creature",
    "effects": "effect",
    "materials": "material",
}


class SemanticAssetScorer:
    """Estimate game-asset value and category from the local ontology.

    Unknown labels intentionally receive a neutral score floor and no category,
    because the curated ontology is incomplete. Classification is therefore an
    assistive signal rather than a hard rejection rule.
    """

    def __init__(self, engine: SemanticEngine | None = None) -> None:
        self.engine = engine or SemanticEngine()
        terms: set[str] = set()
        categories: dict[str, str] = {}

        for concept in self.engine.concepts.values():
            for group_key, entries in concept.get("groups", {}).items():
                if group_key not in self.engine.DETECTABLE_GROUPS:
                    continue
                category = CATEGORY_MAP.get(group_key)
                for entry in entries:
                    for value in (entry.get("en", ""), entry.get("zh", "")):
                        normalized = self._normalize(value)
                        if not normalized:
                            continue
                        terms.add(normalized)
                        if category:
                            categories.setdefault(normalized, category)

        self.terms = tuple(sorted(terms))
        self.categories = categories

    def score(self, label: str) -> float:
        normalized = self._normalize(label)
        if not normalized:
            return 0.45

        if normalized in self.terms:
            return 1.0

        substring_score = 0.0
        for term in self.terms:
            if min(len(term), len(normalized)) < 3:
                continue
            if term in normalized or normalized in term:
                substring_score = 0.86
                break
        if substring_score:
            return substring_score

        best_ratio = 0.0
        for term in self.terms:
            best_ratio = max(best_ratio, SequenceMatcher(None, normalized, term).ratio())

        if best_ratio >= 0.86:
            return 0.78
        if best_ratio >= 0.72:
            return 0.64
        return 0.45

    def category(self, label: str) -> str | None:
        normalized = self._normalize(label)
        if not normalized:
            return None
        exact = self.categories.get(normalized)
        if exact:
            return exact

        # For generated names such as "rusty ticket gate" or split labels such
        # as "tree_part_a", prefer the longest ontology term contained in the
        # label. Longest-first avoids choosing a broad term when a specific one
        # also matches.
        substring_matches = [
            term
            for term in self.categories
            if min(len(term), len(normalized)) >= 3
            and (term in normalized or normalized in term)
        ]
        if substring_matches:
            best = max(substring_matches, key=len)
            return self.categories[best]

        best_ratio = 0.0
        best_term: str | None = None
        for term in self.categories:
            ratio = SequenceMatcher(None, normalized, term).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_term = term
        if best_term is not None and best_ratio >= 0.90:
            return self.categories[best_term]
        return None

    @staticmethod
    def _normalize(value: str) -> str:
        return "".join(ch.lower() for ch in value.strip() if ch.isalnum())


@lru_cache(maxsize=1)
def _default_scorer() -> SemanticAssetScorer:
    return SemanticAssetScorer()


@lru_cache(maxsize=2048)
def semantic_asset_value(label: str) -> float:
    return _default_scorer().score(label)


@lru_cache(maxsize=2048)
def semantic_asset_category(label: str) -> str | None:
    return _default_scorer().category(label)
