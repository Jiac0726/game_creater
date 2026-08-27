from __future__ import annotations

from difflib import SequenceMatcher
from functools import lru_cache

from app.services.semantic_engine import SemanticEngine


class SemanticAssetScorer:
    """Estimate whether a label resembles a reusable game asset in the ontology.

    Unknown labels intentionally receive a neutral floor instead of zero because
    the curated ontology is still small. The score is evidence for ranking, not
    a hard allow/deny decision.
    """

    def __init__(self, engine: SemanticEngine | None = None) -> None:
        self.engine = engine or SemanticEngine()
        terms: set[str] = set()
        for concept in self.engine.concepts.values():
            for group_key, entries in concept.get("groups", {}).items():
                if group_key not in self.engine.DETECTABLE_GROUPS:
                    continue
                for entry in entries:
                    for value in (entry.get("en", ""), entry.get("zh", "")):
                        normalized = self._normalize(value)
                        if normalized:
                            terms.add(normalized)
        self.terms = tuple(sorted(terms))

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

    @staticmethod
    def _normalize(value: str) -> str:
        return "".join(ch.lower() for ch in value.strip() if ch.isalnum())


@lru_cache(maxsize=1)
def _default_scorer() -> SemanticAssetScorer:
    return SemanticAssetScorer()


@lru_cache(maxsize=2048)
def semantic_asset_value(label: str) -> float:
    return _default_scorer().score(label)
