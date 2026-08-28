from __future__ import annotations

import math
import os
import re
from difflib import SequenceMatcher
from pathlib import Path

from PIL import Image

from app.asset_library_models import LibraryAsset
from app.services.asset_library import AssetLibrary
from app.services.semantic_engine import SemanticEngine
from app.smart_asset_search_models import (
    SimilarAssetRequest,
    SmartAssetSearchHit,
    SmartAssetSearchRequest,
    SmartAssetSearchResponse,
    SmartSearchProviderStatus,
)


class SmartAssetSearchService:
    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace)
        self.library = AssetLibrary(self.workspace)
        self.semantic = SemanticEngine()

    def providers(self) -> list[SmartSearchProviderStatus]:
        openclip_url = os.getenv("GAME_CREATER_OPENCLIP_URL", "").strip()
        return [
            SmartSearchProviderStatus(
                id="ontology_lexical",
                ready=True,
                kind="text",
                description="Offline Game Asset Ontology expansion plus weighted metadata matching.",
            ),
            SmartSearchProviderStatus(
                id="perceptual_dhash",
                ready=True,
                kind="image",
                description="Dependency-light active-image dHash similarity search.",
            ),
            SmartSearchProviderStatus(
                id="openclip_optional",
                ready=bool(openclip_url),
                kind="multimodal",
                description="Optional OpenCLIP adapter slot; core search does not require GPU dependencies.",
            ),
        ]

    def search(self, request: SmartAssetSearchRequest) -> SmartAssetSearchResponse:
        query = request.query.strip()
        if not query:
            raise ValueError("Search query cannot be empty")
        assets = self._all_assets()
        if request.category:
            assets = [item for item in assets if item.category == request.category]
        if request.min_asset_score is not None:
            assets = [item for item in assets if item.asset_score >= request.min_asset_score]

        terms = self._expanded_terms(query)
        hits = [self._score_text_asset(query, terms, asset) for asset in assets]
        hits = [item for item in hits if item.score > 0.02]
        hits.sort(key=lambda item: (-item.score, -item.asset.asset_score, item.asset.name.lower()))
        return SmartAssetSearchResponse(
            query=query,
            expanded_terms=terms,
            hits=hits[: request.limit],
            providers=["ontology_lexical"],
        )

    def similar(self, request: SimilarAssetRequest) -> SmartAssetSearchResponse:
        seed = self.library.get(request.asset_id)
        seed_path = self.workspace / seed.image_path
        if not seed_path.is_file():
            raise FileNotFoundError(seed_path)
        seed_hash = self._dhash(seed_path)
        hits: list[SmartAssetSearchHit] = []
        for asset in self._all_assets():
            if asset.id == seed.id:
                continue
            path = self.workspace / asset.image_path
            if not path.is_file():
                continue
            try:
                image_score = 1.0 - self._hamming(seed_hash, self._dhash(path)) / 64.0
            except OSError:
                continue
            metadata_score = self._metadata_similarity(seed, asset) if request.include_metadata_similarity else 0.0
            score = min(1.0, max(0.0, image_score * 0.82 + metadata_score * 0.18))
            reasons = [f"视觉相似 {image_score:.2f}"]
            if metadata_score > 0.25:
                reasons.append(f"元数据相似 {metadata_score:.2f}")
            hits.append(
                SmartAssetSearchHit(
                    asset=asset,
                    score=round(score, 4),
                    image_url=f"/workspace/{asset.image_path}",
                    reasons=reasons,
                )
            )
        hits.sort(key=lambda item: (-item.score, -item.asset.asset_score, item.asset.name.lower()))
        return SmartAssetSearchResponse(
            query=f"similar:{seed.id}",
            expanded_terms=[seed.name, seed.category, *seed.tags],
            hits=hits[: request.limit],
            providers=["perceptual_dhash", "metadata_similarity"] if request.include_metadata_similarity else ["perceptual_dhash"],
        )

    def _all_assets(self) -> list[LibraryAsset]:
        result: list[LibraryAsset] = []
        offset = 0
        while True:
            page = self.library.search(limit=200, offset=offset)
            result.extend(page.items)
            offset += len(page.items)
            if not page.items or offset >= page.total:
                break
        return [item for item in result if item.review_state.value != "archived"]

    def _expanded_terms(self, query: str) -> list[str]:
        terms: list[str] = [query]
        try:
            expansion = self.semantic.expand(query, depth=2, max_per_group=8)
            if expansion.matched_concept:
                terms.extend([expansion.matched_concept, expansion.matched_concept_label or ""])
            terms.extend(expansion.modifiers)
            for group in expansion.groups:
                terms.extend([group.key, group.label_zh])
                for item in group.items[:6]:
                    terms.extend([item.zh, item.en])
        except ValueError:
            pass
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in terms:
            value = (raw or "").strip()
            key = self._norm(value)
            if value and key and key not in seen:
                seen.add(key)
                cleaned.append(value)
        return cleaned[:80]

    def _score_text_asset(self, query: str, terms: list[str], asset: LibraryAsset) -> SmartAssetSearchHit:
        fields = [asset.name, asset.category, asset.subcategory, asset.notes or "", *asset.tags]
        provenance = asset.provenance or {}
        prompts = provenance.get("prompts") or []
        if isinstance(prompts, list):
            fields.extend(str(item) for item in prompts)
        text = " ".join(item for item in fields if item).lower()
        normalized_text = self._norm(text)
        normalized_query = self._norm(query)
        score = 0.0
        reasons: list[str] = []

        if normalized_query and normalized_query in normalized_text:
            score += 0.55
            reasons.append("直接文本命中")

        name_ratio = SequenceMatcher(None, normalized_query, self._norm(asset.name)).ratio() if normalized_query else 0.0
        if name_ratio >= 0.45:
            score += min(0.22, name_ratio * 0.22)
            reasons.append(f"名称相似 {name_ratio:.2f}")

        term_hits = 0
        exact_tags = {self._norm(tag) for tag in asset.tags}
        for term in terms:
            key = self._norm(term)
            if not key:
                continue
            if key in exact_tags:
                score += 0.10
                term_hits += 1
            elif key in normalized_text:
                score += 0.025
                term_hits += 1
        if term_hits:
            reasons.append(f"语义扩展命中 {term_hits}")

        category_terms = {self._norm(term) for term in terms}
        if self._norm(asset.category) in category_terms:
            score += 0.12
            reasons.append("类别匹配")

        score += min(0.08, max(0.0, asset.asset_score) * 0.08)
        if asset.favorite:
            score += 0.025
        score = 1.0 - math.exp(-max(0.0, score))
        return SmartAssetSearchHit(
            asset=asset,
            score=round(min(1.0, score), 4),
            image_url=f"/workspace/{asset.image_path}",
            reasons=reasons[:5],
        )

    @staticmethod
    def _metadata_similarity(a: LibraryAsset, b: LibraryAsset) -> float:
        score = 0.0
        weight = 0.0
        weight += 0.35
        if a.category == b.category:
            score += 0.35
        weight += 0.15
        if a.subcategory and a.subcategory == b.subcategory:
            score += 0.15
        a_tags = {item.lower() for item in a.tags}
        b_tags = {item.lower() for item in b.tags}
        weight += 0.35
        if a_tags or b_tags:
            union = a_tags | b_tags
            score += 0.35 * (len(a_tags & b_tags) / max(1, len(union)))
        weight += 0.15
        ratio = SequenceMatcher(None, a.name.lower(), b.name.lower()).ratio()
        score += 0.15 * ratio
        return score / max(weight, 1e-9)

    @staticmethod
    def _dhash(path: Path) -> int:
        with Image.open(path) as image:
            gray = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
            pixels = list(gray.getdata())
        value = 0
        bit = 0
        for y in range(8):
            row = y * 9
            for x in range(8):
                if pixels[row + x] > pixels[row + x + 1]:
                    value |= 1 << bit
                bit += 1
        return value

    @staticmethod
    def _hamming(a: int, b: int) -> int:
        return (a ^ b).bit_count()

    @staticmethod
    def _norm(value: str) -> str:
        return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", value.lower())
