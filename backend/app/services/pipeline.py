from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List
from uuid import uuid4

import numpy as np
from PIL import Image, ImageDraw

from app.models import AssetRecord, BBox, SceneManifest
from app.services.asset_scoring import score_asset
from app.services.grounded_sam2_local import GroundedSam2LocalAdapter
from app.services.semantic_scoring import semantic_asset_value


@dataclass
class Detection:
    label: str
    confidence: float
    bbox: tuple[int, int, int, int]


class AssetSplitPipeline:
    """Game asset splitting pipeline with a pluggable inference backend."""

    _OVERLAY_COLORS = (
        (74, 159, 245),
        (255, 132, 94),
        (125, 220, 153),
        (205, 148, 255),
        (255, 211, 92),
        (94, 224, 219),
    )

    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.mode = os.getenv("GAME_CREATER_MODE", "mock").strip().lower()
        self._grounded_adapter: GroundedSam2LocalAdapter | None = None

    def health(self) -> dict[str, Any]:
        if self.mode == "mock":
            return {
                "backend": "mock",
                "ready": True,
                "loaded": True,
                "device": "cpu",
                "checks": {},
            }
        if self.mode in {"grounded_sam2", "grounded_sam2_local"}:
            return self._get_grounded_adapter().status()
        return {
            "backend": self.mode,
            "ready": False,
            "loaded": False,
            "device": None,
            "checks": {"supported_mode": False},
        }

    def run(self, image_path: str | Path, prompts: Iterable[str]) -> SceneManifest:
        prompts = [p.strip() for p in prompts if p.strip()]
        if not prompts:
            prompts = ["asset"]

        image_path = Path(image_path)
        image = Image.open(image_path).convert("RGBA")
        scene_id = uuid4().hex[:12]
        project_dir = self.workspace / scene_id
        asset_dir = project_dir / "assets"
        mask_dir = project_dir / "masks"
        preview_dir = project_dir / "preview"
        source_dir = project_dir / "source"
        asset_dir.mkdir(parents=True, exist_ok=True)
        mask_dir.mkdir(parents=True, exist_ok=True)
        preview_dir.mkdir(parents=True, exist_ok=True)
        source_dir.mkdir(parents=True, exist_ok=True)

        source_suffix = image_path.suffix.lower() or ".png"
        source_file = f"source/source{source_suffix}"
        shutil.copy2(image_path, project_dir / source_file)

        if self.mode == "mock":
            detections = self._mock_detect(image.width, image.height, prompts)
            masks = [self._rect_mask(image.width, image.height, d.bbox) for d in detections]
        elif self.mode in {"grounded_sam2", "grounded_sam2_local"}:
            detections, masks = self._grounded_sam2(image_path, prompts)
        else:
            raise ValueError(f"Unsupported GAME_CREATER_MODE={self.mode!r}")

        assets: List[AssetRecord] = []
        counters: dict[str, int] = {}
        for detection, mask in zip(detections, masks):
            slug = self._slug(detection.label)
            counters[slug] = counters.get(slug, 0) + 1
            stem = f"{slug}_{counters[slug]:03d}"

            x1, y1, x2, y2 = detection.bbox
            bbox = BBox(x1=x1, y1=y1, x2=x2, y2=y2)
            asset_score, score_components = score_asset(
                mask=mask,
                confidence=detection.confidence,
                scene_width=image.width,
                scene_height=image.height,
                bbox=bbox,
                semantic_value=semantic_asset_value(detection.label),
            )

            alpha = Image.fromarray((mask.astype(np.uint8) * 255), mode="L")
            rgba = image.copy()
            rgba.putalpha(alpha)
            cropped = rgba.crop((x1, y1, x2, y2))
            cropped.save(asset_dir / f"{stem}.png")
            alpha.crop((x1, y1, x2, y2)).save(mask_dir / f"{stem}.png")

            assets.append(
                AssetRecord(
                    id=f"asset_{len(assets)+1:04d}",
                    label=detection.label,
                    confidence=detection.confidence,
                    asset_score=asset_score,
                    score_components=score_components,
                    bbox=bbox,
                    image=f"assets/{stem}.png",
                    mask=f"masks/{stem}.png",
                    source_position={"x": x1, "y": y1},
                )
            )

        preview_path = preview_dir / "overlay.png"
        self._save_overlay(image, detections, masks, preview_path)

        manifest = SceneManifest(
            scene_id=scene_id,
            source_image=image_path.name,
            width=image.width,
            height=image.height,
            mode=self.mode,
            prompts=prompts,
            assets=assets,
            preview_image="preview/overlay.png",
            source_file=source_file,
        )
        (project_dir / "scene.json").write_text(
            json.dumps(manifest.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return manifest

    def _mock_detect(self, width: int, height: int, prompts: list[str]) -> list[Detection]:
        """Generate deterministic boxes solely to validate the product workflow."""
        detections: list[Detection] = []
        n = min(len(prompts), 6)
        cell_w = max(width // max(n, 1), 1)
        margin_x = max(width // 50, 2)
        margin_y = max(height // 12, 2)

        for index, label in enumerate(prompts[:n]):
            x1 = min(index * cell_w + margin_x, width - 1)
            x2 = min((index + 1) * cell_w - margin_x, width)
            y1 = margin_y
            y2 = max(height - margin_y, y1 + 1)
            if x2 <= x1:
                x2 = min(x1 + 1, width)
            detections.append(Detection(label=label, confidence=0.5, bbox=(x1, y1, x2, y2)))
        return detections

    @staticmethod
    def _rect_mask(width: int, height: int, bbox: tuple[int, int, int, int]) -> np.ndarray:
        mask = np.zeros((height, width), dtype=bool)
        x1, y1, x2, y2 = bbox
        mask[y1:y2, x1:x2] = True
        return mask

    def _grounded_sam2(
        self,
        image_path: Path,
        prompts: list[str],
    ) -> tuple[list[Detection], list[np.ndarray]]:
        raw_detections, masks = self._get_grounded_adapter().predict(image_path, prompts)
        detections = [
            Detection(
                label=item.label,
                confidence=item.confidence,
                bbox=item.bbox,
            )
            for item in raw_detections
        ]
        return detections, masks

    def _get_grounded_adapter(self) -> GroundedSam2LocalAdapter:
        if self._grounded_adapter is None:
            self._grounded_adapter = GroundedSam2LocalAdapter()
        return self._grounded_adapter

    def _save_overlay(
        self,
        image: Image.Image,
        detections: list[Detection],
        masks: list[np.ndarray],
        output_path: Path,
    ) -> None:
        rgba = np.asarray(image.convert("RGBA"), dtype=np.float32).copy()
        height, width = rgba.shape[:2]

        for index, mask in enumerate(masks):
            normalized = np.asarray(mask, dtype=bool)
            if normalized.shape != (height, width):
                continue
            color = np.asarray(self._OVERLAY_COLORS[index % len(self._OVERLAY_COLORS)], dtype=np.float32)
            rgba[normalized, :3] = rgba[normalized, :3] * 0.62 + color * 0.38

        overlay = Image.fromarray(np.clip(rgba, 0, 255).astype(np.uint8), mode="RGBA")
        draw = ImageDraw.Draw(overlay)
        line_width = max(2, min(width, height) // 300)

        for index, detection in enumerate(detections):
            color = self._OVERLAY_COLORS[index % len(self._OVERLAY_COLORS)]
            x1, y1, x2, y2 = detection.bbox
            draw.rectangle((x1, y1, x2, y2), outline=color + (255,), width=line_width)
            label = f"{detection.label} {detection.confidence:.2f}"
            text_y = y1 + 4 if y1 < 18 else y1 - 16
            draw.text((x1 + 4, text_y), label, fill=color + (255,))

        overlay.save(output_path)

    @staticmethod
    def _slug(value: str) -> str:
        safe = "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")
        return safe or "asset"
