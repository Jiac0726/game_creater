from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import numpy as np
from PIL import Image, ImageFilter

from app.models import AssetRecord
from app.services.asset_library import AssetLibrary
from app.services.birefnet_sidecar import BiRefNetSidecarClient
from app.services.scene_store import AssetNotFoundError, SceneStore


class EdgeRefinementService:
    """Refine only the soft alpha around an existing SAM mask boundary.

    The binary mask and bbox remain unchanged. The refined RGBA is stored as a
    new asset version instead of overwriting the original segmented PNG.
    """

    def __init__(
        self,
        workspace: str | Path,
        client: BiRefNetSidecarClient | None = None,
    ) -> None:
        self.workspace = Path(workspace)
        self.store = SceneStore(self.workspace)
        self.library = AssetLibrary(self.workspace)
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
        inside_band = mask_arr & band
        refined[inside_band] = np.maximum(refined[inside_band], 128)

        local = refined[offset_y : offset_y + height, offset_x : offset_x + width]
        if local.shape != (height, width):
            raise ValueError("Refined alpha crop does not match asset dimensions")

        rgba = source.crop((x1, y1, x2, y2)).convert("RGBA")
        alpha_image = Image.fromarray(local, mode="L")
        rgba.putalpha(alpha_image)

        versions_dir = scene_dir / "versions"
        versions_dir.mkdir(parents=True, exist_ok=True)
        token = uuid4().hex[:8]
        image_rel = f"versions/{asset.id}_birefnet_{token}.png"
        alpha_rel = f"versions/{asset.id}_birefnet_{token}_alpha.png"
        rgba.save(scene_dir / image_rel)
        alpha_image.save(scene_dir / alpha_rel)

        asset.image = image_rel
        asset.alpha = alpha_rel
        self.store.save(manifest)

        if asset.library_asset_id:
            self.library.add_version(
                asset.library_asset_id,
                kind="birefnet_refined",
                image_path=f"{scene_id}/{image_rel}",
                mask_path=f"{scene_id}/{asset.mask}",
                alpha_path=f"{scene_id}/{alpha_rel}",
                metadata={
                    "radius": radius,
                    "hard_mask_unchanged": True,
                    "bbox_unchanged": True,
                },
                activate=True,
            )
        return asset

    @staticmethod
    def _asset(assets: list[AssetRecord], asset_id: str) -> AssetRecord:
        for asset in assets:
            if asset.id == asset_id:
                return asset
        raise AssetNotFoundError(asset_id)
