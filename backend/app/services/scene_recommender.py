from __future__ import annotations

import re

from app.models import (
    MissingAssetRecommendation,
    SceneManifest,
    SceneRecommendations,
    SemanticExpansion,
)


class SceneRecommender:
    """Compare detected scene assets with ontology-derived candidate assets."""

    DETECTABLE_GROUPS = {
        "buildings",
        "structures",
        "props",
        "vegetation",
        "terrain",
        "vehicles",
        "creatures",
    }

    def recommend(
        self,
        manifest: SceneManifest,
        expansion: SemanticExpansion,
        max_results: int = 20,
        min_semantic_score: float = 0.65,
    ) -> SceneRecommendations:
        if expansion.matched_concept is None:
            raise ValueError("Cannot recommend missing assets without a matched ontology concept")

        max_results = max(1, min(int(max_results), 100))
        min_semantic_score = max(0.0, min(float(min_semantic_score), 1.0))

        detected_labels = [asset.label.strip() for asset in manifest.assets if asset.label.strip()]
        candidates: list[tuple[str, str, str, str, float]] = []
        seen: set[str] = set()

        for group in expansion.groups:
            if group.key not in self.DETECTABLE_GROUPS:
                continue
            for item in group.items:
                if item.source.startswith("variant:"):
                    continue
                if item.score < min_semantic_score:
                    continue
                key = self._normalize(item.en)
                if not key or key in seen:
                    continue
                seen.add(key)
                candidates.append((item.zh, item.en, group.key, group.label_zh, item.score))

        matched_count = 0
        missing: list[MissingAssetRecommendation] = []
        for zh, en, group_key, group_label, score in candidates:
            if self._is_present(zh, en, detected_labels):
                matched_count += 1
                continue
            missing.append(
                MissingAssetRecommendation(
                    zh=zh,
                    en=en,
                    group=group_key,
                    group_label_zh=group_label,
                    semantic_score=score,
                )
            )

        missing.sort(key=lambda item: (-item.semantic_score, item.group, item.en.lower()))
        candidate_count = len(candidates)
        coverage_ratio = round(matched_count / candidate_count, 4) if candidate_count else 0.0

        return SceneRecommendations(
            scene_id=manifest.scene_id,
            keyword=expansion.input,
            matched_concept_label=expansion.matched_concept_label,
            detected_labels=detected_labels,
            candidate_count=candidate_count,
            matched_count=matched_count,
            coverage_ratio=coverage_ratio,
            missing=missing[:max_results],
        )

    def _is_present(self, zh: str, en: str, detected_labels: list[str]) -> bool:
        candidate_values = [self._normalize(en), self._normalize(zh)]
        for detected in detected_labels:
            detected_norm = self._normalize(detected)
            if not detected_norm:
                continue
            for candidate in candidate_values:
                if not candidate:
                    continue
                if candidate == detected_norm:
                    return True
                if len(candidate) >= 4 and (candidate in detected_norm or detected_norm in candidate):
                    return True
                if self._token_overlap(candidate, detected_norm) >= 0.75:
                    return True
        return False

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(
            token
            for token in re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", " ", value.lower()).split()
            if token
        )

    @staticmethod
    def _token_overlap(left: str, right: str) -> float:
        left_tokens = set(left.split())
        right_tokens = set(right.split())
        if not left_tokens or not right_tokens:
            return 0.0
        intersection = len(left_tokens & right_tokens)
        return intersection / max(1, min(len(left_tokens), len(right_tokens)))
