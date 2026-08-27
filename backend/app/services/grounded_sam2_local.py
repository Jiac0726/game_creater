from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class AdapterDetection:
    label: str
    confidence: float
    bbox: tuple[int, int, int, int]


class GroundedSam2LocalAdapter:
    """Lazy local GroundingDINO + SAM2/SAM2.1 adapter.

    Heavy dependencies are imported only when this adapter is selected, so the
    core FastAPI application can still run in mock mode without torch/CUDA.
    """

    def __init__(self) -> None:
        self.gdino_config = os.getenv("GROUNDING_DINO_CONFIG", "").strip()
        self.gdino_checkpoint = os.getenv("GROUNDING_DINO_CHECKPOINT", "").strip()
        self.sam2_config = os.getenv(
            "SAM2_MODEL_CONFIG",
            "configs/sam2.1/sam2.1_hiera_l.yaml",
        ).strip()
        self.sam2_checkpoint = os.getenv("SAM2_CHECKPOINT", "").strip()
        self.requested_device = os.getenv("GAME_CREATER_DEVICE", "auto").strip().lower()
        self.box_threshold = float(os.getenv("GAME_CREATER_BOX_THRESHOLD", "0.35"))
        self.text_threshold = float(os.getenv("GAME_CREATER_TEXT_THRESHOLD", "0.25"))

        self._torch: Any | None = None
        self._box_convert: Any | None = None
        self._load_image: Any | None = None
        self._predict: Any | None = None
        self._grounding_model: Any | None = None
        self._sam2_predictor: Any | None = None
        self._device: str | None = None

    def status(self) -> dict[str, Any]:
        checks = {
            "torch": importlib.util.find_spec("torch") is not None,
            "sam2": importlib.util.find_spec("sam2") is not None,
            "grounding_dino": importlib.util.find_spec("grounding_dino") is not None,
            "gdino_config": self._file_exists(self.gdino_config),
            "gdino_checkpoint": self._file_exists(self.gdino_checkpoint),
            "sam2_checkpoint": self._file_exists(self.sam2_checkpoint),
            "sam2_config": bool(self.sam2_config),
        }
        ready = all(checks.values())
        resolved_device = None
        cuda_available = None

        if checks["torch"]:
            try:
                import torch

                cuda_available = bool(torch.cuda.is_available())
                resolved_device = self._resolve_device(torch)
            except Exception:
                pass

        return {
            "backend": "grounded_sam2_local",
            "ready": ready,
            "loaded": self._grounding_model is not None and self._sam2_predictor is not None,
            "device_requested": self.requested_device,
            "device": self._device or resolved_device,
            "cuda_available": cuda_available,
            "box_threshold": self.box_threshold,
            "text_threshold": self.text_threshold,
            "checks": checks,
        }

    def predict(
        self,
        image_path: str | Path,
        prompts: list[str],
    ) -> tuple[list[AdapterDetection], list[np.ndarray]]:
        self._ensure_loaded()

        assert self._torch is not None
        assert self._box_convert is not None
        assert self._load_image is not None
        assert self._predict is not None
        assert self._grounding_model is not None
        assert self._sam2_predictor is not None
        assert self._device is not None

        image_source, image_tensor = self._load_image(str(image_path))
        self._sam2_predictor.set_image(image_source)

        caption = self._caption(prompts)
        boxes, confidences, labels = self._predict(
            model=self._grounding_model,
            image=image_tensor,
            caption=caption,
            box_threshold=self.box_threshold,
            text_threshold=self.text_threshold,
            device=self._device,
        )

        if getattr(boxes, "numel", lambda: 0)() == 0:
            return [], []

        height, width = image_source.shape[:2]
        scale = self._torch.tensor([width, height, width, height], dtype=boxes.dtype)
        input_boxes = self._box_convert(
            boxes=boxes.detach().cpu() * scale,
            in_fmt="cxcywh",
            out_fmt="xyxy",
        ).numpy()

        masks, _, _ = self._sam2_predictor.predict(
            point_coords=None,
            point_labels=None,
            box=input_boxes,
            multimask_output=False,
        )

        masks = np.asarray(masks)
        if masks.ndim == 4:
            masks = masks.squeeze(1)
        elif masks.ndim == 2:
            masks = masks[None, ...]

        score_values = (
            confidences.detach().cpu().tolist()
            if hasattr(confidences, "detach")
            else list(confidences)
        )
        label_values = list(labels)

        detections: list[AdapterDetection] = []
        normalized_masks: list[np.ndarray] = []

        for box, score, label, mask in zip(
            input_boxes,
            score_values,
            label_values,
            masks,
        ):
            x1, y1, x2, y2 = self._clip_box(box, width, height)
            if x2 <= x1 or y2 <= y1:
                continue
            detections.append(
                AdapterDetection(
                    label=str(label).strip() or "asset",
                    confidence=float(score),
                    bbox=(x1, y1, x2, y2),
                )
            )
            normalized_masks.append(np.asarray(mask, dtype=bool))

        return detections, normalized_masks

    def _ensure_loaded(self) -> None:
        if self._grounding_model is not None and self._sam2_predictor is not None:
            return

        status = self.status()
        if not status["ready"]:
            missing = [name for name, ok in status["checks"].items() if not ok]
            raise RuntimeError(
                "Grounded-SAM2 local backend is not ready. Missing: "
                + ", ".join(missing)
                + ". See README 'Grounded-SAM2 local mode'."
            )

        import torch
        from torchvision.ops import box_convert
        from sam2.build_sam import build_sam2
        from sam2.sam2_image_predictor import SAM2ImagePredictor
        from grounding_dino.groundingdino.util.inference import (
            load_image,
            load_model,
            predict,
        )

        self._torch = torch
        self._box_convert = box_convert
        self._load_image = load_image
        self._predict = predict
        self._device = self._resolve_device(torch)

        self._grounding_model = load_model(
            model_config_path=self.gdino_config,
            model_checkpoint_path=self.gdino_checkpoint,
            device=self._device,
        )

        sam2_model = build_sam2(
            self.sam2_config,
            self.sam2_checkpoint,
            device=self._device,
        )
        self._sam2_predictor = SAM2ImagePredictor(sam2_model)

    def _resolve_device(self, torch: Any) -> str:
        if self.requested_device in {"cuda", "cpu"}:
            if self.requested_device == "cuda" and not torch.cuda.is_available():
                raise RuntimeError(
                    "GAME_CREATER_DEVICE=cuda was requested, but CUDA is unavailable."
                )
            return self.requested_device
        return "cuda" if torch.cuda.is_available() else "cpu"

    @staticmethod
    def _caption(prompts: list[str]) -> str:
        cleaned = [p.strip().lower().rstrip(".") for p in prompts if p.strip()]
        return ". ".join(cleaned) + "."

    @staticmethod
    def _file_exists(value: str) -> bool:
        return bool(value) and Path(value).expanduser().is_file()

    @staticmethod
    def _clip_box(
        box: np.ndarray,
        width: int,
        height: int,
    ) -> tuple[int, int, int, int]:
        x1, y1, x2, y2 = [float(v) for v in box]
        x1 = max(0, min(width - 1, int(round(x1))))
        y1 = max(0, min(height - 1, int(round(y1))))
        x2 = max(x1 + 1, min(width, int(round(x2))))
        y2 = max(y1 + 1, min(height, int(round(y2))))
        return x1, y1, x2, y2
