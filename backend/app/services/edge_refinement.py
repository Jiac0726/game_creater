from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from app.models import AssetRecord
from app.services.birefnet_sidecar import BiRefNetSidecarClient
from app.services.scene_store import AssetNotFoundError, SceneStore


class EdgeRefinementService:
    """Refine only the soft alpha around an existing SAM mask boundary.

    The binary mask and bbox remain unchanged. BiRefNet receives a padded crop
    for visual context, but its prediction is gated by a narrow dilation/erosion
    band derived from the SAM mask. This prevents a foreground model from
    replacing the semantic ownership already decided by GroundingDINO + SAM2.
    """

    def __init__(
        self,
        workspace: str | Path,
        client: BiRefNetSidecarClient | None = None,
    ) -> None:
        self.workspace = Path(workspace)
        self.store = SceneStore(self.workspace)
        self.client = client or BiRefNetSidecarClient()

    def health(self) -> dict:
        return self.client.health()

    def refine(self, scene_id: str, asset_id: str, radius: int = 6) -> AssetRecord:
        manifest = self.store.load(scene_id)
        asset = self._asset(manifest.assets, asset_id)
        scene_dir = self.workspace / scene_id

        if not manifest.source_file:
            raise ValueError("Scene has no retained source image")
        source_path = scene_dir / manifest.source_file
        mask_path = scene_dir / asset.mask
        image_path = scene_dir / asset.image
        if not source_path.is_file():
            raise ValueError("Retained source image is missing")
        if not mask_path.is_file():
            raise ValueError("Asset mask is missing")

        x1, y1, x2, y2 = asset.bbox.x1, asset.bbox.y1, asset.bbox.x2, asset.bbox.y2
        width = x2 - x1
        height = y2 - y1
        if width <= 0 or height <= 0:
            raise ValueError("Asset bbox is empty")

        radius = max(1, min(int(radius), 24))
        padding = max(16, radius * 3)
        cx1 = max(0, x1 - padding)
        cy1 = max(0, y1 - padding)
        cx2 = min(manifest.width, x2 + padding)
        cy2 = min(manifest.height, y2 + padding)

        source = Image.open(source_path).convert("RGBA")
        context_rgb = source.crop((cx1, cy1, cx2, cy2)).convert("RGB")
        predicted = self.client.predict_alpha(context_rgb)
        if predicted.size != context_rgb.size:
            predicted = predicted.resize(context_rgb.size, Image.Resampling.BILINEAR)

        binary_crop = Image.open(mask_path).convert("L")
        if binary_crop.size != (width, height):
            binary_crop = binary_crop.resize((width, height), Image.Resampling.NEAREST)

        context_mask = Image.new("L", context_rgb.size, 0)
        offset_x = x1 - cx1
        offset_y = y1 - cy1
        context_mask.paste(binary_crop, (offset_x, offset_y))

        kernel = radius * 2 + 1
        dilated = context_mask.filter(ImageFilter.MaxFilter(kernel))
        eroded = context_mask.filter(ImageFilter.MinFilter(kernel))

        mask_arr = np.asarray(context_mask, dtype=np.uint8) >= 128
        support = np.asarray(dilated, dtype=np.uint8) > 0
        core = np.asarray(eroded, dtype=np.uint8) >= 128
        pred = np.asarray(predicted, dtype=np.uint8)

        refined = np.zeros_like(pred, dtype=np.uint8)
        refined[core] = 255
        band = support & ~core
        refined[band] = pred[band]

        # Do not let an uncertain foreground model erase pixels that SAM already
        # considered part of the object. In the boundary band, keep a modest
        # interior alpha floor while still allowing soft semi-transparent edges.
        inside_band = mask_arr & band
        refined[inside_band] = np.maximum(refined[inside_band], 128)

        local = refined[offset_y : offset_y + height, offset_x : offset_x + width]
        if local.shape != (height, width):
            raise ValueError("Refined alpha crop does not match asset dimensions")

        rgba = source.crop((x1, y1, x2, y2)).convert("RGBA")
        rgba.putalpha(Image.fromarray(local, mode="L"))
        image_path.parent.mkdir(parents=True, exist_ok=True)
        rgba.save(image_path)
        return asset

    @staticmethod
    def _asset(assets: list[AssetRecord], asset_id: str) -> AssetRecord:
        for asset in assets:
            if asset.id == asset_id:
                return asset
        raise AssetNotFoundError(asset_id)
