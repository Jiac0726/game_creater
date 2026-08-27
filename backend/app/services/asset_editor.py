from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from app.models import (
    AssetMergeRequest,
    AssetRecord,
    AssetSplitRequest,
    BBox,
    SceneManifest,
)
from app.services.asset_scoring import score_asset
from app.services.scene_store import AssetNotFoundError, SceneStore
from app.services.semantic_scoring import semantic_asset_value


class AssetEditor:
    """Edit normalized game assets without depending on an inference model.

    Operations rebuild transparent PNGs, cropped masks, scene.json and the
    overlay from the retained source image. This keeps manual correction
    independent from GroundingDINO/SAM2.
    """

    _COLORS = (
        (74, 159, 245),
        (255, 132, 94),
        (125, 220, 153),
        (205, 148, 255),
        (255, 211, 92),
        (94, 224, 219),
    )

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace)
        self.store = SceneStore(self.workspace)

    def delete(self, scene_id: str, asset_id: str) -> SceneManifest:
        manifest = self.store.load(scene_id)
        asset = self._asset(manifest, asset_id)
        scene_dir = self.workspace / scene_id

        manifest.assets = [item for item in manifest.assets if item.id != asset_id]
        self._delete_asset_files(scene_dir, asset)
        self.store.save(manifest)
        self._rebuild_overlay(manifest)
        return self.store.load(scene_id)

    def merge(self, scene_id: str, request: AssetMergeRequest) -> SceneManifest:
        unique_ids = list(dict.fromkeys(request.asset_ids))
        if len(unique_ids) < 2:
            raise ValueError("Merge requires at least two different assets")

        label = request.label.strip()
        if not label:
            raise ValueError("Merged asset label cannot be empty")

        manifest = self.store.load(scene_id)
        scene_dir = self.workspace / scene_id
        assets = [self._asset(manifest, asset_id) for asset_id in unique_ids]

        union = np.zeros((manifest.height, manifest.width), dtype=bool)
        for asset in assets:
            union |= self._full_mask(scene_dir, manifest, asset)
        if not union.any():
            raise ValueError("Selected assets have empty masks")

        categories = {asset.category for asset in assets}
        category = request.category.strip() if request.category else None
        if not category:
            category = categories.pop() if len(categories) == 1 else "uncategorized"

        merged = self._write_asset(
            manifest=manifest,
            mask=union,
            label=label,
            category=category,
            confidence=sum(item.confidence for item in assets) / len(assets),
            notes=request.notes,
        )

        if not request.keep_sources:
            selected = set(unique_ids)
            manifest.assets = [item for item in manifest.assets if item.id not in selected]
            for asset in assets:
                self._delete_asset_files(scene_dir, asset)

        manifest.assets.append(merged)
        self.store.save(manifest)
        self._rebuild_overlay(manifest)
        return self.store.load(scene_id)

    def split(
        self,
        scene_id: str,
        asset_id: str,
        request: AssetSplitRequest,
    ) -> SceneManifest:
        manifest = self.store.load(scene_id)
        scene_dir = self.workspace / scene_id
        asset = self._asset(manifest, asset_id)
        rect = request.rect

        if not (0 <= rect.x1 < rect.x2 <= manifest.width):
            raise ValueError("Split rectangle x coordinates are outside the scene")
        if not (0 <= rect.y1 < rect.y2 <= manifest.height):
            raise ValueError("Split rectangle y coordinates are outside the scene")

        original = self._full_mask(scene_dir, manifest, asset)
        selector = np.zeros_like(original)
        selector[rect.y1 : rect.y2, rect.x1 : rect.x2] = True

        inside = original & selector
        outside = original & ~selector
        if not inside.any() or not outside.any():
            raise ValueError("Split rectangle must divide the asset into two non-empty parts")

        inside_label = (request.inside_label or f"{asset.label}_part_a").strip()
        outside_label = (request.outside_label or f"{asset.label}_part_b").strip()
        if not inside_label or not outside_label:
            raise ValueError("Split asset labels cannot be empty")

        part_ids = self._next_asset_ids(manifest, 2)
        part_a = self._write_asset(
            manifest=manifest,
            mask=inside,
            label=inside_label,
            category=asset.category,
            confidence=asset.confidence,
            notes=asset.notes,
            asset_id=part_ids[0],
        )
        part_b = self._write_asset(
            manifest=manifest,
            mask=outside,
            label=outside_label,
            category=asset.category,
            confidence=asset.confidence,
            notes=asset.notes,
            asset_id=part_ids[1],
        )

        manifest.assets = [item for item in manifest.assets if item.id != asset_id]
        self._delete_asset_files(scene_dir, asset)
        manifest.assets.extend([part_a, part_b])
        self.store.save(manifest)
        self._rebuild_overlay(manifest)
        return self.store.load(scene_id)

    def _write_asset(
        self,
        manifest: SceneManifest,
        mask: np.ndarray,
        label: str,
        category: str,
        confidence: float,
        notes: str | None,
        asset_id: str | None = None,
    ) -> AssetRecord:
        scene_dir = self.workspace / manifest.scene_id
        source = self._source_image(manifest)
        bbox = self._bbox_from_mask(mask)
        asset_id = asset_id or self._next_asset_id(manifest)
        stem = f"{asset_id}_{self._slug(label)}"
        asset_score, score_components = score_asset(
            mask=mask,
            confidence=confidence,
            scene_width=manifest.width,
            scene_height=manifest.height,
            bbox=bbox,
            semantic_value=semantic_asset_value(label),
        )

        alpha = Image.fromarray(mask.astype(np.uint8) * 255, mode="L")
        rgba = source.copy()
        rgba.putalpha(alpha)
        crop_box = (bbox.x1, bbox.y1, bbox.x2, bbox.y2)

        image_rel = f"assets/{stem}.png"
        mask_rel = f"masks/{stem}.png"
        rgba.crop(crop_box).save(scene_dir / image_rel)
        alpha.crop(crop_box).save(scene_dir / mask_rel)

        return AssetRecord(
            id=asset_id,
            label=label,
            category=category or "uncategorized",
            confidence=float(confidence),
            asset_score=asset_score,
            score_components=score_components,
            bbox=bbox,
            image=image_rel,
            mask=mask_rel,
            source_position={"x": bbox.x1, "y": bbox.y1},
            notes=notes,
        )

    def _source_image(self, manifest: SceneManifest) -> Image.Image:
        if not manifest.source_file:
            raise ValueError("Scene has no retained source image; analyze the scene again")
        path = self.workspace / manifest.scene_id / manifest.source_file
        if not path.is_file():
            raise ValueError("Retained source image is missing; analyze the scene again")
        return Image.open(path).convert("RGBA")

    def _full_mask(
        self,
        scene_dir: Path,
        manifest: SceneManifest,
        asset: AssetRecord,
    ) -> np.ndarray:
        mask_path = scene_dir / asset.mask
        if not mask_path.is_file():
            raise ValueError(f"Mask file is missing for {asset.id}")

        cropped = Image.open(mask_path).convert("L")
        expected = (asset.bbox.x2 - asset.bbox.x1, asset.bbox.y2 - asset.bbox.y1)
        if cropped.size != expected:
            cropped = cropped.resize(expected, resample=Image.Resampling.NEAREST)

        full = np.zeros((manifest.height, manifest.width), dtype=bool)
        data = np.asarray(cropped, dtype=np.uint8) > 0
        full[asset.bbox.y1 : asset.bbox.y2, asset.bbox.x1 : asset.bbox.x2] = data
        return full

    def _rebuild_overlay(self, manifest: SceneManifest) -> None:
        scene_dir = self.workspace / manifest.scene_id
        source = np.asarray(self._source_image(manifest), dtype=np.float32).copy()
        height, width = source.shape[:2]

        for index, asset in enumerate(manifest.assets):
            mask = self._full_mask(scene_dir, manifest, asset)
            color = np.asarray(self._COLORS[index % len(self._COLORS)], dtype=np.float32)
            source[mask, :3] = source[mask, :3] * 0.62 + color * 0.38

        overlay = Image.fromarray(np.clip(source, 0, 255).astype(np.uint8), mode="RGBA")
        draw = ImageDraw.Draw(overlay)
        line_width = max(2, min(width, height) // 300)
        for index, asset in enumerate(manifest.assets):
            color = self._COLORS[index % len(self._COLORS)]
            box = (asset.bbox.x1, asset.bbox.y1, asset.bbox.x2, asset.bbox.y2)
            draw.rectangle(box, outline=color + (255,), width=line_width)
            draw.text(
                (asset.bbox.x1 + 4, max(0, asset.bbox.y1 - 16)),
                f"{asset.label} {asset.confidence:.2f}",
                fill=color + (255,),
            )

        preview_rel = manifest.preview_image or "preview/overlay.png"
        preview_path = scene_dir / preview_rel
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        overlay.save(preview_path)
        manifest.preview_image = preview_rel
        self.store.save(manifest)

    @staticmethod
    def _asset(manifest: SceneManifest, asset_id: str) -> AssetRecord:
        for asset in manifest.assets:
            if asset.id == asset_id:
                return asset
        raise AssetNotFoundError(asset_id)

    @staticmethod
    def _bbox_from_mask(mask: np.ndarray) -> BBox:
        ys, xs = np.nonzero(mask)
        if len(xs) == 0:
            raise ValueError("Mask is empty")
        return BBox(
            x1=int(xs.min()),
            y1=int(ys.min()),
            x2=int(xs.max()) + 1,
            y2=int(ys.max()) + 1,
        )

    @staticmethod
    def _next_asset_ids(manifest: SceneManifest, count: int) -> list[str]:
        max_id = 0
        for asset in manifest.assets:
            try:
                max_id = max(max_id, int(asset.id.rsplit("_", 1)[-1]))
            except (TypeError, ValueError):
                continue
        return [f"asset_{max_id + offset:04d}" for offset in range(1, count + 1)]

    @classmethod
    def _next_asset_id(cls, manifest: SceneManifest) -> str:
        return cls._next_asset_ids(manifest, 1)[0]

    @staticmethod
    def _delete_asset_files(scene_dir: Path, asset: AssetRecord) -> None:
        for rel in (asset.image, asset.mask):
            path = scene_dir / rel
            if path.is_file():
                path.unlink()

    @staticmethod
    def _slug(value: str) -> str:
        safe = "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")
        return safe or "asset"
