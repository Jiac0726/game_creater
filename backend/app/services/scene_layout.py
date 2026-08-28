from __future__ import annotations

from app.models import AssetRecord, SceneManifest


class SceneLayoutBuilder:
    """Build an engine-neutral 2D scene layout from normalized assets.

    Coordinates remain in source-image pixels. The visual anchor is the bbox
    bottom-center so top-down/side-view engines can use ``sort_y`` as a useful
    first-pass painter-order signal without losing exact source placement.
    """

    FORMAT = "game-creater-scene-layout"
    VERSION = 1

    def build(self, manifest: SceneManifest) -> dict:
        return {
            "format": self.FORMAT,
            "version": self.VERSION,
            "scene_id": manifest.scene_id,
            "source_size": {
                "width": manifest.width,
                "height": manifest.height,
            },
            "coordinate_system": {
                "origin": "top-left",
                "x_positive": "right",
                "y_positive": "down",
                "unit": "source_pixel",
            },
            "placement": {
                "anchor": "bbox_bottom_center",
                "default_sort": "sort_y_ascending_back_to_front",
            },
            "assets": [self._asset_entry(asset) for asset in manifest.assets],
        }

    @staticmethod
    def _asset_entry(asset: AssetRecord) -> dict:
        width = asset.bbox.x2 - asset.bbox.x1
        height = asset.bbox.y2 - asset.bbox.y1
        center_x = (asset.bbox.x1 + asset.bbox.x2) / 2.0
        bottom_y = float(asset.bbox.y2)
        return {
            "id": asset.id,
            "label": asset.label,
            "category": asset.category,
            "image": asset.image,
            "mask": asset.mask,
            "bbox": asset.bbox.model_dump(),
            "size": {"width": width, "height": height},
            "anchor": {
                "type": "bottom_center",
                "normalized": [0.5, 1.0],
                "position": [center_x, bottom_y],
            },
            "texture_offset": [0.0, -height / 2.0],
            "sort_y": bottom_y,
            "confidence": asset.confidence,
            "asset_score": asset.asset_score,
            "notes": asset.notes,
        }
