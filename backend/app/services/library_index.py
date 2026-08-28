from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from app.models import SceneManifest


SCENE_DIRECTORY_PATTERN = re.compile(r"^[0-9a-f]{12}$")


class LibraryIndex:
    """Build a safe, read-only index of persisted scene manifests."""

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace)

    def build(self) -> dict:
        scenes: list[dict] = []
        category_counts: Counter[str] = Counter()
        total_assets = 0

        if not self.workspace.is_dir():
            return {"scenes": [], "asset_count": 0, "category_counts": {}}

        for scene_dir in self.workspace.iterdir():
            if not scene_dir.is_dir() or not SCENE_DIRECTORY_PATTERN.fullmatch(scene_dir.name):
                continue

            manifest_path = scene_dir / "scene.json"
            if not manifest_path.is_file():
                continue

            try:
                manifest = SceneManifest.model_validate_json(
                    manifest_path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                continue
            if not self.manifest_paths_are_safe(manifest):
                continue

            modified_at = datetime.fromtimestamp(
                manifest_path.stat().st_mtime,
                tz=timezone.utc,
            ).isoformat()
            scene_categories = Counter(
                (asset.category or "uncategorized") for asset in manifest.assets
            )
            category_counts.update(scene_categories)
            total_assets += len(manifest.assets)

            scenes.append(
                {
                    "scene_id": manifest.scene_id,
                    "title": self._scene_title(manifest),
                    "relative_path": f"{scene_dir.name}/scene.json",
                    "mode": manifest.mode,
                    "width": manifest.width,
                    "height": manifest.height,
                    "asset_count": len(manifest.assets),
                    "preview_image": manifest.preview_image,
                    "source_file": manifest.source_file,
                    "categories": dict(scene_categories),
                    "modified_at": modified_at,
                }
            )

        scenes.sort(key=lambda scene: scene["modified_at"], reverse=True)
        return {
            "scenes": scenes,
            "asset_count": total_assets,
            "category_counts": dict(category_counts),
        }

    @staticmethod
    def _scene_title(manifest: SceneManifest) -> str:
        if manifest.prompts:
            first = manifest.prompts[0].strip()
            if first:
                return first
        return f"场景 {manifest.scene_id}"

    @classmethod
    def manifest_paths_are_safe(cls, manifest: SceneManifest) -> bool:
        paths = [manifest.preview_image, manifest.source_file]
        for asset in manifest.assets:
            paths.extend([asset.image, asset.mask, asset.alpha])
        return all(path is None or cls._is_safe_relative_path(path) for path in paths)

    @staticmethod
    def _is_safe_relative_path(value: str) -> bool:
        normalized = value.replace("\\", "/")
        path = PurePosixPath(normalized)
        return bool(normalized) and not path.is_absolute() and ".." not in path.parts
