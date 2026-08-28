#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


def mask_iou(a: np.ndarray, b: np.ndarray) -> float:
    intersection = int(np.logical_and(a, b).sum())
    union = int(np.logical_or(a, b).sum())
    return intersection / union if union else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate one exported Game Creater scene directory")
    parser.add_argument("scene_dir", help="workspace/<scene_id> or validation_output/<scene_id>")
    parser.add_argument("--duplicate-iou", type=float, default=0.90)
    args = parser.parse_args()

    scene_dir = Path(args.scene_dir).expanduser().resolve()
    manifest_path = scene_dir / "scene.json"
    if not manifest_path.is_file():
        raise SystemExit(f"scene.json not found: {manifest_path}")

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    width = int(data.get("width", 0))
    height = int(data.get("height", 0))
    assets = data.get("assets") or []
    errors: list[str] = []
    warnings: list[str] = []
    full_masks: list[np.ndarray] = []

    for asset in assets:
        asset_id = str(asset.get("id", "unknown"))
        bbox = asset.get("bbox") or {}
        x1, y1, x2, y2 = [int(bbox.get(key, 0)) for key in ("x1", "y1", "x2", "y2")]
        if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
            errors.append(f"{asset_id}: bbox out of scene bounds: {(x1, y1, x2, y2)}")
            full_masks.append(np.zeros((max(height, 1), max(width, 1)), dtype=bool))
            continue

        image_path = scene_dir / str(asset.get("image", ""))
        mask_path = scene_dir / str(asset.get("mask", ""))
        if not image_path.is_file():
            errors.append(f"{asset_id}: asset image missing: {image_path}")
        if not mask_path.is_file():
            errors.append(f"{asset_id}: mask missing: {mask_path}")
            full_masks.append(np.zeros((height, width), dtype=bool))
            continue

        mask_image = Image.open(mask_path).convert("L")
        expected_size = (x2 - x1, y2 - y1)
        if mask_image.size != expected_size:
            errors.append(f"{asset_id}: mask size {mask_image.size} != bbox size {expected_size}")
        cropped_mask = np.asarray(mask_image, dtype=np.uint8) > 0
        if not cropped_mask.any():
            errors.append(f"{asset_id}: empty mask")

        full = np.zeros((height, width), dtype=bool)
        usable_h = min(cropped_mask.shape[0], y2 - y1)
        usable_w = min(cropped_mask.shape[1], x2 - x1)
        full[y1 : y1 + usable_h, x1 : x1 + usable_w] = cropped_mask[:usable_h, :usable_w]
        full_masks.append(full)

        if image_path.is_file():
            rgba = Image.open(image_path).convert("RGBA")
            if rgba.size != expected_size:
                errors.append(f"{asset_id}: RGBA size {rgba.size} != bbox size {expected_size}")
            alpha = np.asarray(rgba.getchannel("A"), dtype=np.uint8) > 0
            if not alpha.any():
                errors.append(f"{asset_id}: transparent PNG has empty alpha")
            if alpha.shape == cropped_mask.shape:
                disagreement = float(np.logical_xor(alpha, cropped_mask).sum()) / max(1, alpha.size)
                if disagreement > 0.01:
                    warnings.append(f"{asset_id}: PNG alpha differs from mask by {disagreement:.2%}")

    duplicate_pairs: list[dict[str, object]] = []
    threshold = min(1.0, max(0.0, args.duplicate_iou))
    for left in range(len(full_masks)):
        for right in range(left + 1, len(full_masks)):
            overlap = mask_iou(full_masks[left], full_masks[right])
            if overlap >= threshold:
                duplicate_pairs.append(
                    {
                        "left": assets[left].get("id"),
                        "right": assets[right].get("id"),
                        "left_label": assets[left].get("label"),
                        "right_label": assets[right].get("label"),
                        "mask_iou": round(overlap, 4),
                    }
                )

    scores = [float(item.get("asset_score", 0.0) or 0.0) for item in assets]
    confidences = [float(item.get("confidence", 0.0) or 0.0) for item in assets]
    report = {
        "ok": not errors,
        "scene_id": data.get("scene_id"),
        "scene_size": [width, height],
        "asset_count": len(assets),
        "average_asset_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
        "average_confidence": round(sum(confidences) / len(confidences), 4) if confidences else 0.0,
        "inference_stats": data.get("inference_stats") or {},
        "duplicate_threshold": threshold,
        "duplicate_candidates": duplicate_pairs,
        "errors": errors,
        "warnings": warnings,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
