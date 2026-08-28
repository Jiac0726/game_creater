from __future__ import annotations

import re
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
from PIL import Image

from app.asset_intelligence_models import (
    AssetIntelligenceApplyRequest,
    AssetIntelligenceReport,
    AssetQualityMetric,
    DuplicateCandidate,
)
from app.asset_library_models import LibraryAsset, LibraryAssetPatch
from app.services.asset_library import AssetLibrary
from app.services.semantic_engine import SemanticEngine


class AssetIntelligenceService:
    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace)
        self.library = AssetLibrary(self.workspace)
        self.semantic = SemanticEngine()
        self._ontology_entries = self._build_ontology_entries()

    def status(self) -> dict:
        return {
            "ready": True,
            "offline": True,
            "features": ["classification", "tag_suggestions", "quality", "duplicate_detection"],
            "ontology_entries": len(self._ontology_entries),
        }

    def analyze(self, asset_id: str, *, duplicate_threshold: float = 0.90) -> AssetIntelligenceReport:
        asset = self.library.get(asset_id)
        image_path = self.workspace / asset.image_path
        if not image_path.is_file():
            raise FileNotFoundError(image_path)

        category, subcategory, tags = self._classify(asset)
        metrics, issues, quality = self._quality(image_path)
        duplicates = self._duplicates(asset, image_path, duplicate_threshold)
        return AssetIntelligenceReport(
            asset_id=asset.id,
            suggested_category=category,
            suggested_subcategory=subcategory,
            suggested_tags=tags,
            quality_score=quality,
            quality_metrics=metrics,
            issues=issues,
            duplicate_candidates=duplicates,
        )

    def analyze_bulk(self, asset_ids: list[str], *, duplicate_threshold: float = 0.90) -> list[AssetIntelligenceReport]:
        return [self.analyze(asset_id, duplicate_threshold=duplicate_threshold) for asset_id in asset_ids]

    def apply(self, asset_id: str, request: AssetIntelligenceApplyRequest) -> LibraryAsset:
        if request.report.asset_id != asset_id:
            raise ValueError("Report asset_id does not match target asset")
        current = self.library.get(asset_id)
        tags = list(current.tags)
        if request.add_tags:
            seen = {item.lower() for item in tags}
            for tag in request.report.suggested_tags:
                if tag.lower() not in seen:
                    tags.append(tag)
                    seen.add(tag.lower())
        patch = LibraryAssetPatch(
            category=request.report.suggested_category if request.apply_category else None,
            subcategory=request.report.suggested_subcategory if request.apply_subcategory else None,
            tags=tags if request.add_tags else None,
        )
        return self.library.patch(asset_id, patch)

    def _classify(self, asset: LibraryAsset) -> tuple[str, str, list[str]]:
        haystack = " ".join([asset.name, asset.category, asset.subcategory, *asset.tags, asset.notes or ""])
        norm = self._norm(haystack)
        scores: dict[str, float] = defaultdict(float)
        tags: list[str] = []
        tag_seen: set[str] = set()
        best_label = ""
        best_score = 0.0

        for group, concept, zh, en in self._ontology_entries:
            zh_key = self._norm(zh)
            en_key = self._norm(en)
            local = 0.0
            if zh_key and zh_key in norm:
                local = max(local, 1.0)
            if en_key and en_key in norm:
                local = max(local, 1.0)
            if local == 0.0:
                for candidate in (zh_key, en_key):
                    if candidate:
                        ratio = SequenceMatcher(None, self._norm(asset.name), candidate).ratio()
                        if ratio >= 0.72:
                            local = max(local, ratio * 0.75)
            if local <= 0:
                continue
            scores[group] += local
            if local > best_score:
                best_score = local
                best_label = en or zh
            for raw in (concept, zh, en, group):
                value = (raw or "").strip()
                key = value.lower()
                if value and key not in tag_seen:
                    tag_seen.add(key)
                    tags.append(value)

        if scores:
            category = max(scores.items(), key=lambda item: item[1])[0]
        else:
            category = asset.category if asset.category != "uncategorized" else "uncategorized"
        subcategory = best_label.lower().replace(" ", "_") if best_label else asset.subcategory

        provenance = asset.provenance or {}
        prompts = provenance.get("prompts") or []
        if isinstance(prompts, list):
            for prompt in prompts[:8]:
                value = str(prompt).strip()
                key = value.lower()
                if value and key not in tag_seen:
                    tag_seen.add(key)
                    tags.append(value)
        return category, subcategory, tags[:24]

    def _quality(self, path: Path) -> tuple[list[AssetQualityMetric], list[str], float]:
        with Image.open(path) as source:
            rgba = source.convert("RGBA")
            alpha = np.asarray(rgba.getchannel("A"), dtype=np.uint8)
            width, height = rgba.size
        filled = alpha > 0
        fill_ratio = float(filled.mean()) if filled.size else 0.0
        min_dim = min(width, height)
        resolution_score = min(1.0, min_dim / 128.0)
        if fill_ratio <= 0.0:
            fill_score = 0.0
        elif fill_ratio < 0.03:
            fill_score = max(0.1, fill_ratio / 0.03)
        elif fill_ratio > 0.97:
            fill_score = 0.70
        else:
            fill_score = 1.0
        touches = False
        if filled.any():
            touches = bool(filled[0].any() or filled[-1].any() or filled[:, 0].any() or filled[:, -1].any())
        edge_score = 0.55 if touches else 1.0
        ratio = max(width, height) / max(1, min(width, height))
        aspect_score = 1.0 if ratio <= 4.0 else max(0.4, 4.0 / ratio)
        transparency_score = 1.0 if np.any(alpha < 255) else 0.75

        metrics = [
            AssetQualityMetric(key="resolution", value=float(min_dim), score=resolution_score, note="minimum pixel dimension"),
            AssetQualityMetric(key="fill_ratio", value=round(fill_ratio, 4), score=fill_score, note="non-transparent coverage"),
            AssetQualityMetric(key="edge_clearance", value=0.0 if touches else 1.0, score=edge_score, note="sprite touches image edge" if touches else "clear border"),
            AssetQualityMetric(key="aspect_ratio", value=round(ratio, 4), score=aspect_score),
            AssetQualityMetric(key="transparency", value=float(np.mean(alpha < 255)), score=transparency_score),
        ]
        issues: list[str] = []
        if resolution_score < 0.5:
            issues.append("分辨率偏低")
        if fill_ratio <= 0.01:
            issues.append("素材几乎为空")
        elif fill_ratio > 0.97:
            issues.append("几乎没有透明背景")
        if touches:
            issues.append("有效像素触碰图片边缘，可能需要 Padding")
        if ratio > 6.0:
            issues.append("宽高比极端")
        quality = resolution_score * 0.30 + fill_score * 0.25 + edge_score * 0.20 + aspect_score * 0.10 + transparency_score * 0.15
        return metrics, issues, round(min(1.0, max(0.0, quality)), 4)

    def _duplicates(self, seed: LibraryAsset, seed_path: Path, threshold: float) -> list[DuplicateCandidate]:
        seed_hash = self._dhash(seed_path)
        result: list[DuplicateCandidate] = []
        for asset in self._all_assets():
            if asset.id == seed.id:
                continue
            path = self.workspace / asset.image_path
            if not path.is_file():
                continue
            try:
                similarity = 1.0 - ((seed_hash ^ self._dhash(path)).bit_count() / 64.0)
            except OSError:
                continue
            if similarity >= threshold:
                result.append(DuplicateCandidate(asset_id=asset.id, name=asset.name, visual_similarity=round(similarity, 4)))
        result.sort(key=lambda item: (-item.visual_similarity, item.name.lower()))
        return result[:20]

    def _all_assets(self) -> list[LibraryAsset]:
        assets: list[LibraryAsset] = []
        offset = 0
        while True:
            page = self.library.search(limit=200, offset=offset)
            assets.extend(page.items)
            offset += len(page.items)
            if not page.items or offset >= page.total:
                break
        return [item for item in assets if item.review_state.value != "archived"]

    def _build_ontology_entries(self) -> list[tuple[str, str, str, str]]:
        result: list[tuple[str, str, str, str]] = []
        for concept_key, concept in self.semantic.concepts.items():
            for group, entries in concept.get("groups", {}).items():
                for entry in entries:
                    result.append((group, concept_key, entry.get("zh", ""), entry.get("en", "")))
        return result

    @staticmethod
    def _dhash(path: Path) -> int:
        with Image.open(path) as image:
            gray = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
            pixels = list(gray.getdata())
        value = 0
        bit = 0
        for y in range(8):
            base = y * 9
            for x in range(8):
                if pixels[base + x] > pixels[base + x + 1]:
                    value |= 1 << bit
                bit += 1
        return value

    @staticmethod
    def _norm(value: str) -> str:
        return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", value.lower())
