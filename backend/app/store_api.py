from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.services.asset_library import LibraryAssetNotFoundError
from app.services.store_payments import StorePaymentError
from app.services.store_service import (
    StoreEntitlementNotFoundError,
    StoreListingNotFoundError,
    StoreOrderNotFoundError,
    StoreService,
)
from app.store_models import (
    StoreCart,
    StoreCheckoutRequest,
    StoreListing,
    StoreListingCreate,
    StoreListingPatch,
    StoreOrder,
    StoreSearchResult,
    StoreStats,
)


def build_store_router(workspace: str | Path) -> APIRouter:
    router = APIRouter(prefix="/store", tags=["asset-store"])
    store = StoreService(workspace)

    @router.get("/stats", response_model=StoreStats)
    def stats() -> StoreStats:
        return store.stats()

    @router.get("/payment/providers")
    def payment_providers() -> dict:
        return {"providers": store.payment_catalog()}

    @router.get("/listings", response_model=StoreSearchResult)
    def listings(
        q: str = "",
        category: str | None = None,
        license_type: str | None = None,
        free_only: bool = False,
        featured: bool | None = None,
        limit: int = Query(default=60, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> StoreSearchResult:
        return store.search_listings(
            query=q,
            category=category,
            license_type=license_type,
            free_only=free_only,
            featured=featured,
            limit=limit,
            offset=offset,
        )

    @router.get("/listings/{listing_id}", response_model=StoreListing)
    def listing(listing_id: str) -> StoreListing:
        try:
            return store.get_listing(listing_id)
        except StoreListingNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Store listing not found") from exc

    @router.get("/seller/listings", response_model=StoreSearchResult)
    def seller_listings(
        limit: int = Query(default=100, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> StoreSearchResult:
        return store.search_listings(limit=limit, offset=offset, include_unpublished=True)

    @router.post("/seller/listings", response_model=StoreListing)
    def create_listing(request: StoreListingCreate) -> StoreListing:
        try:
            return store.create_listing(request)
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Asset Library item not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.patch("/seller/listings/{listing_id}", response_model=StoreListing)
    def patch_listing(listing_id: str, patch: StoreListingPatch) -> StoreListing:
        try:
            return store.patch_listing(listing_id, patch)
        except StoreListingNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Store listing not found") from exc
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Asset Library item not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/cart", response_model=StoreCart)
    def cart() -> StoreCart:
        return store.get_cart()

    @router.post("/cart/{listing_id}", response_model=StoreCart)
    def add_cart(listing_id: str) -> StoreCart:
        try:
            return store.add_to_cart(listing_id)
        except StoreListingNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Store listing not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.delete("/cart/{listing_id}", response_model=StoreCart)
    def remove_cart(listing_id: str) -> StoreCart:
        return store.remove_from_cart(listing_id)

    @router.post("/checkout", response_model=StoreOrder)
    def checkout(request: StoreCheckoutRequest) -> StoreOrder:
        try:
            return store.checkout(request)
        except StoreListingNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Store listing not found") from exc
        except StorePaymentError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/orders", response_model=list[StoreOrder])
    def orders() -> list[StoreOrder]:
        return store.list_orders()

    @router.get("/orders/{order_id}", response_model=StoreOrder)
    def order(order_id: str) -> StoreOrder:
        try:
            return store.get_order(order_id)
        except StoreOrderNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Order not found") from exc

    @router.get("/library")
    def purchased_library() -> dict:
        return {"entitlements": store.list_entitlements()}

    @router.get("/downloads/{entitlement_id}")
    def download(entitlement_id: str) -> FileResponse:
        try:
            archive_path, record = store.build_download(entitlement_id)
        except StoreEntitlementNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Entitlement not found") from exc
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Purchased asset is no longer indexed") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return FileResponse(
            path=archive_path,
            media_type="application/zip",
            filename=f"game_creater_asset_{record.asset_id}_v{record.asset_version}.zip",
            headers={"X-Game-Creater-Download-Id": record.id},
        )

    return router
