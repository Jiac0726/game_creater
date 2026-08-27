from __future__ import annotations

from pathlib import Path

from app.models import AssetPatch, AssetRecord, SceneManifest


class SceneNotFoundError(FileNotFoundError):
    pass


class AssetNotFoundError(KeyError):
    pass


class SceneStore:
    """Persistence helper for scene.json and editable asset metadata."""

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace)

    def load(self, scene_id: str) -> SceneManifest:
        manifest_path = self.workspace / scene_id / "scene.json"
        if not manifest_path.is_file():
            raise SceneNotFoundError(scene_id)
        return SceneManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))

    def save(self, manifest: SceneManifest) -> SceneManifest:
        scene_dir = self.workspace / manifest.scene_id
        if not scene_dir.is_dir():
            raise SceneNotFoundError(manifest.scene_id)

        manifest_path = scene_dir / "scene.json"
        manifest_path.write_text(
            manifest.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return manifest

    def patch_asset(
        self,
        scene_id: str,
        asset_id: str,
        patch: AssetPatch,
    ) -> AssetRecord:
        manifest = self.load(scene_id)

        for index, asset in enumerate(manifest.assets):
            if asset.id != asset_id:
                continue

            updates = patch.model_dump(exclude_unset=True)
            if "label" in updates:
                label = (updates["label"] or "").strip()
                if not label:
                    raise ValueError("Asset label cannot be empty")
                updates["label"] = label

            if "category" in updates:
                category = (updates["category"] or "uncategorized").strip()
                updates["category"] = category or "uncategorized"

            updated = asset.model_copy(update=updates)
            manifest.assets[index] = updated
            self.save(manifest)
            return updated

        raise AssetNotFoundError(asset_id)
