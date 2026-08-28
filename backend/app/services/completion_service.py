from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import numpy as np
from PIL import Image

from app.completion_models import AssetCompletionRequest, AssetCompletionResult
from app.models import AssetRecord, BBox, SceneManifest
from app.services.completion_providers import CompletionProviderRegistry
from app.services.pipeline import AssetSplitPipeline
from app.services.scene_store import AssetNotFoundError, SceneStore


class CompletionService:
    """Complete a user-marked missing/occluded region without overwriting source assets."""

    def __init__(self, workspace: str | Path, pipeline: AssetSplitPipeline) -> None:
        self.workspace = Path(workspace)
        self.pipeline = pipeline
        self.store = SceneStore(self.workspace)
        self.providers = CompletionProviderRegistry()

    def health(self) -> list[dict]:
        return self.providers.catalog()

    def complete(
        self,
        scene_id: str,
        asset_id: str,
        request: AssetCompletionRequest,
    ) -> AssetCompletionResult:
        manifest = self.store.load(scene_id)
        asset = self._asset(manifest, asset_id)
        self._validate_rect(manifest, request.rect)
        scene_dir = self.workspace / scene_id
        source_path = scene_dir / (manifest.source_file or "")
        if not manifest.source_file or not source_path.is_file():
            raise ValueError("Retained source image is missing")

        source = Image.open(source_path).convert("RGBA")
        full_mask = self._full_mask(scene_dir, manifest, asset)
        completion_mask = np.zeros((manifest.height, manifest.width), dtype=np.uint8)
        rect = request.rect
        completion_mask[rect.y1 : rect.y2, rect.x1 : rect.x2] = 255
        if not completion_mask.any():
            raise ValueError("Completion rectangle is empty")

        provider = self.providers.get(request.provider)
        prompt = (request.prompt or f"Complete the hidden or missing part of {asset.label}").strip()
        completed_scene = provider.inpaint(
            source,
            Image.fromarray(completion_mask, mode="L"),
            prompt=prompt,
            negative_prompt=request.negative_prompt,
        )

        job_id = uuid4().hex[:12]
        completed_dir = scene_dir / "completed"
        completed_dir.mkdir(parents=True, exist_ok=True)
        completed_scene_rel = f"completed/{job_id}_scene.png"
        completed_scene_path = scene_dir / completed_scene_rel
        completed_scene.save(completed_scene_path, format="PNG")

        if self.pipeline.mode in {"grounded_sam2", "grounded_sam2_local"}:
            completed_object_mask, confidence = self._resegment(
                completed_scene_path,
                asset,
                request.rect,
                manifest,
            )
            resegmented = True
        else:
            completed_object_mask = full_mask | (completion_mask > 0)
            confidence = asset.confidence
            resegmented = False

        bbox = self._bbox_from_mask(completed_object_mask)
        alpha = Image.fromarray(completed_object_mask.astype(np.uint8) * 255, mode="L")
        rgba = completed_scene.convert("RGBA")
        rgba.putalpha(alpha)
        crop_box = (bbox.x1, bbox.y1, bbox.x2, bbox.y2)

        asset_rel = f"completed/{job_id}_{self._slug(asset.label)}.png"
        mask_rel = f"completed/{job_id}_{self._slug(asset.label)}_mask.png"
        rgba.crop(crop_box).save(scene_dir / asset_rel)
        alpha.crop(crop_box).save(scene_dir / mask_rel)

        result = AssetCompletionResult(
            job_id=job_id,
            scene_id=scene_id,
            asset_id=asset_id,
            provider=provider.name,
            mode=request.mode,
            rect=request.rect,
            source_asset=asset.image,
            completed_scene=completed_scene_rel,
            completed_asset=asset_rel,
            completed_mask=mask_rel,
            resegmented=resegmented,
            confidence=float(confidence),
            metadata={
                "prompt": prompt,
                "negative_prompt": request.negative_prompt,
                "completed_bbox": bbox.model_dump(),
                "source_pixels_preserved": True,
                "original_asset_unchanged": True,
            },
        )
        (completed_dir / f"{job_id}.json").write_text(
            json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return result

    def _resegment(
        self,
        image_path: Path,
        asset: AssetRecord,
        rect: BBox,
        manifest: SceneManifest,
    ) -> tuple[np.ndarray, float]:
        detections, masks = self.pipeline._get_grounded_adapter().predict(image_path, [asset.label])
        if not detections or not masks:
            raise ValueError(f"Completion succeeded, but {asset.label!r} could not be re-segmented")

        target = (
            min(asset.bbox.x1, rect.x1),
            min(asset.bbox.y1, rect.y1),
            max(asset.bbox.x2, rect.x2),
            max(asset.bbox.y2, rect.y2),
        )
        best_index = max(
            range(len(detections)),
            key=lambda index: (
                self._bbox_iou(detections[index].bbox, target),
                detections[index].confidence,
            ),
        )
        mask = np.asarray(masks[best_index], dtype=bool)
        if mask.shape != (manifest.height, manifest.width) or not mask.any():
            raise ValueError("Re-segmented completion mask is invalid")
        return mask, float(detections[best_index].confidence)

    @staticmethod
    def _asset(manifest: SceneManifest, asset_id: str) -> AssetRecord:
        for asset in manifest.assets:
            if asset.id == asset_id:
                return asset
        raise AssetNotFoundError(asset_id)

    @staticmethod
    def _validate_rect(manifest: SceneManifest, rect: BBox) -> None:
        if not (0 <= rect.x1 < rect.x2 <= manifest.width):
            raise ValueError("Completion rectangle x coordinates are outside the scene")
        if not (0 <= rect.y1 < rect.y2 <= manifest.height):
            raise ValueError("Completion rectangle y coordinates are outside the scene")

    @staticmethod
    def _full_mask(scene_dir: Path, manifest: SceneManifest, asset: AssetRecord) -> np.ndarray:
        path = scene_dir / asset.mask
        if not path.is_file():
            raise ValueError(f"Mask file is missing for {asset.id}")
        cropped = Image.open(path).convert("L")
        expected = (asset.bbox.x2 - asset.bbox.x1, asset.bbox.y2 - asset.bbox.y1)
        if cropped.size != expected:
            cropped = cropped.resize(expected, resample=Image.Resampling.NEAREST)
        full = np.zeros((manifest.height, manifest.width), dtype=bool)
        full[asset.bbox.y1 : asset.bbox.y2, asset.bbox.x1 : asset.bbox.x2] = (
            np.asarray(cropped, dtype=np.uint8) > 0
        )
        return full

    @staticmethod
    def _bbox_from_mask(mask: np.ndarray) -> BBox:
        ys, xs = np.nonzero(mask)
        if not len(xs):
            raise ValueError("Completed mask is empty")
        return BBox(
            x1=int(xs.min()),
            y1=int(ys.min()),
            x2=int(xs.max()) + 1,
            y2=int(ys.max()) + 1,
        )

    @staticmethod
    def _bbox_iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
        intersection = iw * ih
        if not intersection:
            return 0.0
        area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
        area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
        union = area_a + area_b - intersection
        return intersection / union if union else 0.0

    @staticmethod
    def _slug(value: str) -> str:
        safe = "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")
        return safe or "asset"
