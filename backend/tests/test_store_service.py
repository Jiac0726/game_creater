from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from app.asset_library_models import AssetReviewState, LibraryAssetPatch
from app.services.asset_library import AssetLibrary
from app.services.pipeline import AssetSplitPipeline
from app.services.store_service import StoreService
from app.store_models import StoreCheckoutRequest, StoreLicenseType, StoreListingCreate, StoreOrderStatus


def _workspace_with_asset(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GAME_CREATER_MODE", "mock")
    source = tmp_path / "scene.png"
    Image.new("RGB", (180, 120), "white").save(source)
    workspace = tmp_path / "workspace"
    manifest = AssetSplitPipeline(workspace).run(source, ["tree", "crate"])
    library = AssetLibrary(workspace)
    first = manifest.assets[0]
    assert first.library_asset_id
    return workspace, manifest, library, first.library_asset_id


def test_needs_review_asset_cannot_be_published(tmp_path: Path, monkeypatch) -> None:
    workspace, _, _, asset_id = _workspace_with_asset(tmp_path, monkeypatch)
    store = StoreService(workspace)

    with pytest.raises(ValueError, match="approved"):
        store.create_listing(
            StoreListingCreate(
                asset_id=asset_id,
                title="Forest Tree",
                price_minor=1200,
                publish=True,
            )
        )

    draft = store.create_listing(
        StoreListingCreate(
            asset_id=asset_id,
            title="Forest Tree",
            price_minor=1200,
            publish=False,
        )
    )
    assert draft.status.value == "draft"


def test_approved_asset_can_be_published_and_searched(tmp_path: Path, monkeypatch) -> None:
    workspace, _, library, asset_id = _workspace_with_asset(tmp_path, monkeypatch)
    library.patch(
        asset_id,
        LibraryAssetPatch(
            review_state=AssetReviewState.APPROVED,
            category="vegetation",
            tags=["forest", "tree"],
        ),
    )
    store = StoreService(workspace)
    listing = store.create_listing(
        StoreListingCreate(
            asset_id=asset_id,
            title="Ancient Forest Tree",
            description="Transparent environment prop",
            price_minor=990,
            currency="cny",
            license_type=StoreLicenseType.COMMERCIAL,
            featured=True,
        )
    )

    assert listing.status.value == "published"
    assert listing.currency == "CNY"
    assert listing.category == "vegetation"
    assert listing.tags == ["forest", "tree"]

    result = store.search_listings(query="forest", category="vegetation", featured=True)
    assert result.total == 1
    assert result.items[0].id == listing.id


def test_cart_mock_checkout_grants_versioned_entitlement_and_download(tmp_path: Path, monkeypatch) -> None:
    workspace, _, library, asset_id = _workspace_with_asset(tmp_path, monkeypatch)
    library.patch(asset_id, LibraryAssetPatch(review_state=AssetReviewState.PRODUCTION_READY))
    asset_before = library.get(asset_id)
    assert asset_before.active_version == 1

    store = StoreService(workspace)
    assert store.db_path.parent.name == ".game_creater_state"
    assert store.workspace not in store.db_path.parents

    listing = store.create_listing(
        StoreListingCreate(
            asset_id=asset_id,
            title="Production Tree",
            price_minor=2500,
            license_type=StoreLicenseType.COMMERCIAL,
        )
    )
    cart = store.add_to_cart(listing.id)
    assert len(cart.items) == 1
    assert cart.total_minor == 2500

    order = store.checkout(StoreCheckoutRequest(payment_provider="mock"))
    assert order.status == StoreOrderStatus.PAID
    assert order.total_minor == 2500
    assert order.payment_provider == "mock"
    assert order.provider_reference and order.provider_reference.startswith("mock_")
    assert len(order.entitlements) == 1
    entitlement = order.entitlements[0]
    assert entitlement.asset_id == asset_id
    assert entitlement.asset_version == 1
    assert store.get_cart().items == []

    # A later library version must not change the already granted entitlement.
    original_version = library.list_versions(asset_id)[-1]
    new_image = workspace / "manual_v2.png"
    Image.new("RGBA", (32, 32), (255, 0, 0, 255)).save(new_image)
    library.add_version(
        asset_id,
        kind="manual_refine",
        image_path="manual_v2.png",
        metadata={"test": True},
        activate=True,
    )
    assert library.get(asset_id).active_version == 2
    assert store.list_entitlements()[0].asset_version == 1

    archive_path, download = store.build_download(entitlement.id)
    assert archive_path.is_file()
    assert download.asset_version == 1

    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert "asset.png" in names
        assert "metadata.json" in names
        assert "LICENSE.txt" in names
        metadata = json.loads(archive.read("metadata.json").decode("utf-8"))
        assert metadata["asset_version"] == 1
        assert metadata["entitlement_id"] == entitlement.id
        assert archive.read("asset.png") == (workspace / original_version.image_path).read_bytes()

    stats = store.stats()
    assert stats.published_listings == 1
    assert stats.paid_listings == 1
    assert stats.paid_orders == 1
    assert stats.entitlements == 1
    assert stats.downloads == 1
    assert stats.gross_minor == 2500


def test_free_listing_still_creates_entitlement(tmp_path: Path, monkeypatch) -> None:
    workspace, _, library, asset_id = _workspace_with_asset(tmp_path, monkeypatch)
    library.patch(asset_id, LibraryAssetPatch(review_state=AssetReviewState.APPROVED))
    store = StoreService(workspace)
    listing = store.create_listing(
        StoreListingCreate(
            asset_id=asset_id,
            title="Free Starter Prop",
            price_minor=0,
            license_type=StoreLicenseType.PERSONAL,
        )
    )

    order = store.checkout(StoreCheckoutRequest(listing_ids=[listing.id], payment_provider="mock"))
    assert order.status == StoreOrderStatus.PAID
    assert order.total_minor == 0
    assert len(order.entitlements) == 1
    assert order.entitlements[0].license_type == StoreLicenseType.PERSONAL
