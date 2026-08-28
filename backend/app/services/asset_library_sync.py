from __future__ import annotations

from pathlib import Path

from app.asset_library_models import LibraryAsset
from app.models import SceneManifest


def apply_library_metadata_to_scene(workspace: str | Path, asset: LibraryAsset) -> None:
    """Mirror library-managed display metadata back into scene.json.

    This intentionally writes the manifest directly instead of calling
    SceneStore.save(), because SceneStore would immediately re-index the same
    asset while this operation is already inside a library metadata update.
    """
    manifest_path = Path(workspace) / asset.scene_id / "scene.json"
    if not manifest_path.is_file():
        return

    manifest = SceneManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    changed = False
    for item in manifest.assets:
        if item.id != asset.scene_asset_id:
            continue
        item.library_asset_id = asset.id
        item.label = asset.name
        item.category = asset.category
        item.notes = asset.notes
        changed = True
        break

    if changed:
        manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
