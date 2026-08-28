from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.asset_library_models import AssetRelationType, AssetReviewState, LibraryAssetPatch
from app.services.asset_library import AssetLibrary
from app.services.asset_library_sync import apply_library_metadata_to_scene
from app.services.pipeline import AssetSplitPipeline
from app.services.scene_store import SceneStore


def _scene(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GAME_CREATER_MODE", "mock")
    source = tmp_path / "scene.png"
    Image.new("RGB", (180, 120), "white").save(source)
    workspace = tmp_path / "workspace"
    manifest = AssetSplitPipeline(workspace).run(source, ["tree", "crate", "bench"])
    return workspace, manifest


def test_pipeline_auto_registers_assets_with_stable_global_ids(tmp_path: Path, monkeypatch) -> None:
    workspace, manifest = _scene(tmp_path, monkeypatch)
    library = AssetLibrary(workspace)

    assert all(asset.library_asset_id for asset in manifest.assets)
    assert len({asset.library_asset_id for asset in manifest.assets}) == len(manifest.assets)

    first = manifest.assets[0]
    library_asset = library.get(first.library_asset_id)
    assert library_asset.scene_id == manifest.scene_id
    assert library_asset.scene_asset_id == first.id
    assert library_asset.name == first.label
    assert library_asset.image_path == f"{manifest.scene_id}/{first.image}"
    assert library.list_versions(first.library_asset_id)[0].kind == "segmented"

    original_id = first.library_asset_id
    SceneStore(workspace).save(manifest)
    reloaded = SceneStore(workspace).load(manifest.scene_id)
    assert reloaded.assets[0].library_asset_id == original_id
    assert library.get(original_id).id == original_id


def test_asset_library_metadata_tags_search_and_review_state(tmp_path: Path, monkeypatch) -> None:
    workspace, manifest = _scene(tmp_path, monkeypatch)
    library = AssetLibrary(workspace)
    asset_id = manifest.assets[0].library_asset_id
    assert asset_id

    updated = library.patch(
        asset_id,
        LibraryAssetPatch(
            name="Ancient Mossy Tree",
            category="vegetation",
            subcategory="tree",
            review_state=AssetReviewState.APPROVED,
            favorite=True,
            notes="hero vegetation",
            tags=["forest", "moss", "large", "forest"],
        ),
    )
    apply_library_metadata_to_scene(workspace, updated)

    assert updated.name == "Ancient Mossy Tree"
    assert updated.review_state == AssetReviewState.APPROVED
    assert updated.favorite is True
    assert updated.tags == ["forest", "large", "moss"]

    scene_asset = SceneStore(workspace).load(manifest.scene_id).assets[0]
    assert scene_asset.library_asset_id == asset_id
    assert scene_asset.label == "Ancient Mossy Tree"
    assert scene_asset.category == "vegetation"
    assert scene_asset.notes == "hero vegetation"

    # A later Scene save must not revert metadata mirrored from the library.
    scene = SceneStore(workspace).load(manifest.scene_id)
    SceneStore(workspace).save(scene)
    assert library.get(asset_id).name == "Ancient Mossy Tree"
    assert library.get(asset_id).category == "vegetation"

    result = library.search(
        query="Mossy",
        category="vegetation",
        review_state="approved",
        favorite=True,
        tags=["forest", "moss"],
    )
    assert result.total == 1
    assert result.items[0].id == asset_id


def test_collections_relations_versions_and_archiving(tmp_path: Path, monkeypatch) -> None:
    workspace, manifest = _scene(tmp_path, monkeypatch)
    library = AssetLibrary(workspace)
    first_id = manifest.assets[0].library_asset_id
    second_id = manifest.assets[1].library_asset_id
    assert first_id and second_id

    collection = library.create_collection("Magic Forest", "Reusable forest props")
    library.add_to_collection(collection["id"], [first_id, second_id])
    assert library.search(collection_id=collection["id"]).total == 2
    assert library.list_collections()[0]["asset_count"] == 2

    library.add_relation(first_id, second_id, AssetRelationType.RELATED_TO)
    relations = library.relations(first_id)
    assert len(relations) == 1
    assert relations[0]["target_asset_id"] == second_id

    version = library.add_version(
        first_id,
        kind="manual_refine",
        image_path=f"{manifest.scene_id}/assets/refined.png",
        mask_path=f"{manifest.scene_id}/masks/refined.png",
        metadata={"reason": "test"},
        activate=False,
    )
    assert version.version == 2
    versions = library.list_versions(first_id)
    assert [item.version for item in versions] == [2, 1]
    assert library.get(first_id).active_version == 1

    # Removing a scene-local asset does not delete library history; it archives it.
    manifest.assets = [asset for asset in manifest.assets if asset.library_asset_id != second_id]
    SceneStore(workspace).save(manifest)
    archived = library.get(second_id)
    assert archived.review_state == AssetReviewState.ARCHIVED


def test_library_stats(tmp_path: Path, monkeypatch) -> None:
    workspace, manifest = _scene(tmp_path, monkeypatch)
    library = AssetLibrary(workspace)
    first_id = manifest.assets[0].library_asset_id
    assert first_id
    library.patch(first_id, LibraryAssetPatch(review_state=AssetReviewState.PRODUCTION_READY, favorite=True))
    library.create_collection("Production")

    stats = library.stats()
    assert stats.total_assets == len(manifest.assets)
    assert stats.production_ready == 1
    assert stats.favorites == 1
    assert stats.collections == 1
