from __future__ import annotations

import json
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from app.models import SemanticExpansion, SemanticGroup, SemanticKeyword


class SemanticEngine:
    """Offline, data-driven game asset semantic expansion engine.

    No network service or LLM is required. The ontology is intentionally kept
    outside Python code so it can later be grown from curated datasets,
    ConceptNet-derived candidates, embeddings, or user edits without changing
    the API contract.
    """

    DETECTABLE_GROUPS = {
        "buildings",
        "structures",
        "props",
        "vegetation",
        "terrain",
        "vehicles",
        "creatures",
    }
    VARIANT_GROUPS = {
        "buildings",
        "structures",
        "props",
        "vegetation",
        "terrain",
        "vehicles",
    }

    def __init__(self, ontology_path: str | Path | None = None) -> None:
        if ontology_path is None:
            repo_root = Path(__file__).resolve().parents[3]
            ontology_path = repo_root / "data" / "game_asset_ontology.json"
        self.ontology_path = Path(ontology_path)
        self.data = json.loads(self.ontology_path.read_text(encoding="utf-8"))
        self.group_labels: dict[str, str] = self.data.get("group_labels", {})
        self.concepts: dict[str, dict[str, Any]] = self.data.get("concepts", {})
        self.modifiers: dict[str, dict[str, Any]] = self.data.get("modifiers", {})

    def expand(
        self,
        keyword: str,
        depth: int = 2,
        max_per_group: int = 12,
    ) -> SemanticExpansion:
        raw = keyword.strip()
        if not raw:
            raise ValueError("Keyword cannot be empty")

        depth = max(1, min(int(depth), 3))
        max_per_group = max(1, min(int(max_per_group), 30))

        concept_key = self._match_concept(raw)
        modifier_keys = self._match_modifiers(raw)
        warnings: list[str] = []

        if concept_key is None:
            warnings.append(
                "No ontology concept matched this keyword yet. Add an alias/concept to data/game_asset_ontology.json."
            )
            return SemanticExpansion(
                input=raw,
                modifiers=[self.modifiers[key].get("label_zh", key) for key in modifier_keys],
                warnings=warnings,
            )

        concept = self.concepts[concept_key]
        grouped: dict[str, dict[str, SemanticKeyword]] = {}

        for group_key, entries in concept.get("groups", {}).items():
            for index, entry in enumerate(entries):
                self._put(
                    grouped,
                    group_key,
                    SemanticKeyword(
                        zh=entry["zh"],
                        en=entry["en"],
                        score=round(max(0.62, 0.94 - index * 0.018), 4),
                        source=f"concept:{concept_key}",
                    ),
                )

        for modifier_key in modifier_keys:
            modifier = self.modifiers[modifier_key]
            for group_key, entries in modifier.get("additions", {}).items():
                for index, entry in enumerate(entries):
                    self._put(
                        grouped,
                        group_key,
                        SemanticKeyword(
                            zh=entry["zh"],
                            en=entry["en"],
                            score=round(max(0.64, 0.86 - index * 0.02), 4),
                            source=f"modifier:{modifier_key}",
                        ),
                    )

        if depth >= 2 and modifier_keys:
            self._add_state_variants(grouped, modifier_keys, max_per_group, depth)

        groups: list[SemanticGroup] = []
        for group_key in self._ordered_group_keys(grouped):
            items = sorted(
                grouped[group_key].values(),
                key=lambda item: (-item.score, item.en.lower()),
            )[:max_per_group]
            groups.append(
                SemanticGroup(
                    key=group_key,
                    label_zh=self.group_labels.get(group_key, group_key),
                    items=items,
                )
            )

        prompts = self._build_detection_prompts(groups)

        return SemanticExpansion(
            input=raw,
            matched_concept=concept_key,
            matched_concept_label=concept.get("label_zh", concept_key),
            modifiers=[self.modifiers[key].get("label_zh", key) for key in modifier_keys],
            groups=groups,
            detection_prompts=prompts,
            warnings=warnings,
        )

    def catalog(self) -> dict[str, Any]:
        return {
            "concepts": [
                {
                    "key": key,
                    "label_zh": value.get("label_zh", key),
                    "aliases": value.get("aliases", []),
                }
                for key, value in self.concepts.items()
            ],
            "modifiers": [
                {
                    "key": key,
                    "label_zh": value.get("label_zh", key),
                    "aliases": value.get("aliases", []),
                }
                for key, value in self.modifiers.items()
            ],
            "groups": self.group_labels,
        }

    def _match_concept(self, keyword: str) -> str | None:
        normalized = self._normalize(keyword)
        candidates: list[tuple[int, float, str]] = []

        for key, concept in self.concepts.items():
            for alias in concept.get("aliases", []):
                normalized_alias = self._normalize(alias)
                if not normalized_alias:
                    continue
                if normalized_alias in normalized or normalized in normalized_alias:
                    candidates.append((len(normalized_alias), 1.0, key))

        if candidates:
            candidates.sort(reverse=True)
            return candidates[0][2]

        fuzzy: list[tuple[float, str]] = []
        for key, concept in self.concepts.items():
            for alias in concept.get("aliases", []):
                ratio = SequenceMatcher(None, normalized, self._normalize(alias)).ratio()
                fuzzy.append((ratio, key))
        fuzzy.sort(reverse=True)
        return fuzzy[0][1] if fuzzy and fuzzy[0][0] >= 0.68 else None

    def _match_modifiers(self, keyword: str) -> list[str]:
        normalized = self._normalize(keyword)
        matches: list[tuple[int, str]] = []
        for key, modifier in self.modifiers.items():
            best_length = 0
            for alias in modifier.get("aliases", []):
                normalized_alias = self._normalize(alias)
                if normalized_alias and normalized_alias in normalized:
                    best_length = max(best_length, len(normalized_alias))
            if best_length:
                matches.append((best_length, key))
        matches.sort(reverse=True)
        return [key for _, key in matches]

    def _add_state_variants(
        self,
        grouped: dict[str, dict[str, SemanticKeyword]],
        modifier_keys: list[str],
        max_per_group: int,
        depth: int,
    ) -> None:
        # Depth 2 deliberately stays conservative for detector-friendly output;
        # depth 3 explores more art-production variants for brainstorming.
        state_limit = 1 if depth == 2 else None
        base_limit = 2 if depth == 2 else 4

        for modifier_key in modifier_keys:
            states = self.modifiers[modifier_key].get("states", [])
            if state_limit is not None:
                states = states[:state_limit]
            if not states:
                continue
            for group_key in list(grouped.keys()):
                if group_key not in self.VARIANT_GROUPS:
                    continue
                base_items = [
                    item
                    for item in grouped[group_key].values()
                    if not item.source.startswith("variant:")
                ][: max(1, min(base_limit, max_per_group // 2))]
                for state in states:
                    for base in base_items:
                        variant = SemanticKeyword(
                            zh=f"{state['zh']}{base.zh}",
                            en=f"{state['en']} {base.en}",
                            score=round(max(0.5, base.score * 0.80), 4),
                            source=f"variant:{modifier_key}",
                        )
                        self._put(grouped, group_key, variant)

    def _build_detection_prompts(self, groups: list[SemanticGroup]) -> list[str]:
        prompts: list[str] = []
        seen: set[str] = set()

        # Prefer base/addition nouns. State variants are useful for art prompts,
        # but generic object nouns are usually more robust for open-vocabulary detection.
        for include_variants in (False, True):
            for group in groups:
                if group.key not in self.DETECTABLE_GROUPS:
                    continue
                for item in group.items:
                    is_variant = item.source.startswith("variant:")
                    if is_variant != include_variants:
                        continue
                    key = item.en.strip().lower()
                    if not key or key in seen:
                        continue
                    seen.add(key)
                    prompts.append(item.en.strip())
                    if len(prompts) >= 40:
                        return prompts
        return prompts

    def _ordered_group_keys(self, grouped: dict[str, Any]) -> list[str]:
        preferred = [
            "buildings",
            "structures",
            "props",
            "vegetation",
            "terrain",
            "vehicles",
            "creatures",
            "effects",
            "materials",
        ]
        known = [key for key in preferred if key in grouped]
        rest = sorted(key for key in grouped if key not in preferred)
        return known + rest

    @staticmethod
    def _put(
        grouped: dict[str, dict[str, SemanticKeyword]],
        group_key: str,
        item: SemanticKeyword,
    ) -> None:
        bucket = grouped.setdefault(group_key, {})
        dedupe_key = item.en.strip().lower()
        previous = bucket.get(dedupe_key)
        if previous is None or item.score > previous.score:
            bucket[dedupe_key] = item

    @staticmethod
    def _normalize(value: str) -> str:
        return "".join(value.lower().strip().split())
