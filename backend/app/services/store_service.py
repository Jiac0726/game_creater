from __future__ import annotations

import json
import os
import sqlite3
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.asset_library_models import AssetReviewState
from app.services.asset_library import AssetLibrary, LibraryAssetNotFoundError
from app.services.store_payments import StorePaymentError, StorePaymentRegistry
from app.store_models import (
    StoreCart,
    StoreCartItem,
    StoreCheckoutRequest,
    StoreDownloadRecord,
    StoreEntitlement,
    StoreLicenseType,
    StoreListing,
    StoreListingCreate,
    StoreListingPatch,
    StoreListingStatus,
    StoreOrder,
    StoreOrderItem,
    StoreOrderStatus,
    StoreSearchResult,
    StoreStats,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StoreListingNotFoundError(KeyError):
    pass


class StoreOrderNotFoundError(KeyError):
    pass


class StoreEntitlementNotFoundError(KeyError):
    pass


class StoreService:
    """Local-first marketplace domain built on top of Asset Library.

    Public asset binaries stay in workspace. Commerce state lives outside the
    static workspace mount under `.game_creater_state/store.db`.
    """

    PUBLISHABLE_STATES = {
        AssetReviewState.APPROVED.value,
        AssetReviewState.PRODUCTION_READY.value,
        AssetReviewState.IN_USE.value,
    }

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace)
        self.library = AssetLibrary(self.workspace)
        self.state_dir = self.workspace.parent / ".game_creater_state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.state_dir / "store.db"
        self.download_dir = self.state_dir / "downloads"
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.local_user = os.getenv("GAME_CREATER_STORE_USER", "local_user").strip() or "local_user"
        self.payments = StorePaymentRegistry()
        self._init_schema()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _init_schema(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS sellers (
                    id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS listings (
                    id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL,
                    seller_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    price_minor INTEGER NOT NULL DEFAULT 0,
                    currency TEXT NOT NULL DEFAULT 'CNY',
                    license_type TEXT NOT NULL DEFAULT 'commercial',
                    status TEXT NOT NULL DEFAULT 'draft',
                    featured INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(seller_id) REFERENCES sellers(id),
                    UNIQUE(asset_id, seller_id)
                );

                CREATE INDEX IF NOT EXISTS idx_store_listings_status ON listings(status);
                CREATE INDEX IF NOT EXISTS idx_store_listings_asset ON listings(asset_id);

                CREATE TABLE IF NOT EXISTS cart_items (
                    user_id TEXT NOT NULL,
                    listing_id TEXT NOT NULL,
                    added_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, listing_id),
                    FOREIGN KEY(listing_id) REFERENCES listings(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    total_minor INTEGER NOT NULL,
                    currency TEXT NOT NULL,
                    payment_provider TEXT NOT NULL,
                    provider_reference TEXT,
                    payment_metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    paid_at TEXT
                );

                CREATE TABLE IF NOT EXISTS order_items (
                    order_id TEXT NOT NULL,
                    listing_id TEXT NOT NULL,
                    asset_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    price_minor INTEGER NOT NULL,
                    currency TEXT NOT NULL,
                    license_type TEXT NOT NULL,
                    asset_version INTEGER NOT NULL,
                    PRIMARY KEY(order_id, listing_id),
                    FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS entitlements (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    order_id TEXT NOT NULL,
                    listing_id TEXT NOT NULL,
                    asset_id TEXT NOT NULL,
                    license_type TEXT NOT NULL,
                    asset_version INTEGER NOT NULL,
                    granted_at TEXT NOT NULL,
                    UNIQUE(user_id, listing_id),
                    FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_entitlements_user ON entitlements(user_id);

                CREATE TABLE IF NOT EXISTS downloads (
                    id TEXT PRIMARY KEY,
                    entitlement_id TEXT NOT NULL,
                    listing_id TEXT NOT NULL,
                    asset_id TEXT NOT NULL,
                    asset_version INTEGER NOT NULL,
                    downloaded_at TEXT NOT NULL,
                    FOREIGN KEY(entitlement_id) REFERENCES entitlements(id) ON DELETE CASCADE
                );
                """
            )

    def payment_catalog(self) -> list[dict]:
        return self.payments.catalog()

    def create_listing(self, request: StoreListingCreate) -> StoreListing:
        asset = self.library.get(request.asset_id)
        seller_id = self._seller_id(request.seller_name)
        self._ensure_seller(seller_id, request.seller_name)
        status = StoreListingStatus.PUBLISHED if request.publish else StoreListingStatus.DRAFT
        if status == StoreListingStatus.PUBLISHED:
            self._assert_publishable(asset.review_state.value)

        listing_id = f"listing_{uuid4().hex[:16]}"
        now = utc_now()
        title = (request.title or asset.name).strip()
        if not title:
            raise ValueError("Listing title cannot be empty")
        currency = request.currency.upper()

        with self._connect() as db:
            existing = db.execute(
                "SELECT id FROM listings WHERE asset_id=? AND seller_id=?",
                (asset.id, seller_id),
            ).fetchone()
            if existing is not None:
                raise ValueError("This asset already has a listing for the seller")
            db.execute(
                """
                INSERT INTO listings (
                    id, asset_id, seller_id, title, description, price_minor,
                    currency, license_type, status, featured, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    listing_id,
                    asset.id,
                    seller_id,
                    title,
                    request.description.strip(),
                    request.price_minor,
                    currency,
                    request.license_type.value,
                    status.value,
                    int(request.featured),
                    now,
                    now,
                ),
            )
        return self.get_listing(listing_id, include_unpublished=True)

    def patch_listing(self, listing_id: str, patch: StoreListingPatch) -> StoreListing:
        current = self.get_listing(listing_id, include_unpublished=True)
        updates = patch.model_dump(exclude_unset=True)
        if not updates:
            return current

        if "title" in updates:
            title = (updates["title"] or "").strip()
            if not title:
                raise ValueError("Listing title cannot be empty")
            updates["title"] = title
        if "description" in updates:
            updates["description"] = (updates["description"] or "").strip()
        if "currency" in updates and updates["currency"]:
            updates["currency"] = updates["currency"].upper()
        if "license_type" in updates and hasattr(updates["license_type"], "value"):
            updates["license_type"] = updates["license_type"].value
        if "status" in updates and hasattr(updates["status"], "value"):
            updates["status"] = updates["status"].value
        if updates.get("status") == StoreListingStatus.PUBLISHED.value:
            asset = self.library.get(current.asset_id)
            self._assert_publishable(asset.review_state.value)
        if "featured" in updates:
            updates["featured"] = int(bool(updates["featured"]))

        allowed = {"title", "description", "price_minor", "currency", "license_type", "status", "featured"}
        updates = {key: value for key, value in updates.items() if key in allowed}
        if updates:
            assignments = ", ".join(f"{key}=?" for key in updates)
            values = list(updates.values()) + [utc_now(), listing_id]
            with self._connect() as db:
                row = db.execute("SELECT id FROM listings WHERE id=?", (listing_id,)).fetchone()
                if row is None:
                    raise StoreListingNotFoundError(listing_id)
                db.execute(f"UPDATE listings SET {assignments}, updated_at=? WHERE id=?", values)
        return self.get_listing(listing_id, include_unpublished=True)

    def get_listing(self, listing_id: str, *, include_unpublished: bool = False) -> StoreListing:
        with self._connect() as db:
            sql = "SELECT l.*, s.display_name AS seller_name FROM listings l JOIN sellers s ON s.id=l.seller_id WHERE l.id=?"
            params: list = [listing_id]
            if not include_unpublished:
                sql += " AND l.status='published'"
            row = db.execute(sql, params).fetchone()
            if row is None:
                raise StoreListingNotFoundError(listing_id)
            return self._hydrate_listing(db, row)

    def search_listings(
        self,
        *,
        query: str = "",
        category: str | None = None,
        license_type: str | None = None,
        free_only: bool = False,
        featured: bool | None = None,
        limit: int = 60,
        offset: int = 0,
        include_unpublished: bool = False,
    ) -> StoreSearchResult:
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT l.*, s.display_name AS seller_name
                FROM listings l JOIN sellers s ON s.id=l.seller_id
                ORDER BY l.featured DESC, l.updated_at DESC
                """
            ).fetchall()
            items: list[StoreListing] = []
            q = query.strip().lower()
            for row in rows:
                if not include_unpublished and row["status"] != StoreListingStatus.PUBLISHED.value:
                    continue
                try:
                    item = self._hydrate_listing(db, row)
                except LibraryAssetNotFoundError:
                    continue
                if category and item.category != category:
                    continue
                if license_type and item.license_type.value != license_type:
                    continue
                if free_only and item.price_minor != 0:
                    continue
                if featured is not None and item.featured != featured:
                    continue
                if q:
                    haystack = " ".join([item.title, item.description, item.category, " ".join(item.tags)]).lower()
                    if q not in haystack:
                        continue
                items.append(item)
        total = len(items)
        return StoreSearchResult(items=items[offset : offset + limit], total=total, limit=limit, offset=offset)

    def add_to_cart(self, listing_id: str, *, user_id: str | None = None) -> StoreCart:
        user_id = user_id or self.local_user
        listing = self.get_listing(listing_id)
        self._assert_currency_compatible_with_cart(user_id, listing.currency)
        with self._connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO cart_items(user_id, listing_id, added_at) VALUES (?,?,?)",
                (user_id, listing_id, utc_now()),
            )
        return self.get_cart(user_id=user_id)

    def remove_from_cart(self, listing_id: str, *, user_id: str | None = None) -> StoreCart:
        user_id = user_id or self.local_user
        with self._connect() as db:
            db.execute("DELETE FROM cart_items WHERE user_id=? AND listing_id=?", (user_id, listing_id))
        return self.get_cart(user_id=user_id)

    def clear_cart(self, *, user_id: str | None = None) -> None:
        user_id = user_id or self.local_user
        with self._connect() as db:
            db.execute("DELETE FROM cart_items WHERE user_id=?", (user_id,))

    def get_cart(self, *, user_id: str | None = None) -> StoreCart:
        user_id = user_id or self.local_user
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT c.added_at, l.*, s.display_name AS seller_name
                FROM cart_items c
                JOIN listings l ON l.id=c.listing_id
                JOIN sellers s ON s.id=l.seller_id
                WHERE c.user_id=? AND l.status='published'
                ORDER BY c.added_at ASC
                """,
                (user_id,),
            ).fetchall()
            items = [StoreCartItem(listing=self._hydrate_listing(db, row), added_at=row["added_at"]) for row in rows]
        currencies = {item.listing.currency for item in items}
        currency = next(iter(currencies), "CNY")
        total = sum(item.listing.price_minor for item in items)
        return StoreCart(user_id=user_id, items=items, total_minor=total, currency=currency)

    def checkout(self, request: StoreCheckoutRequest, *, user_id: str | None = None) -> StoreOrder:
        user_id = user_id or self.local_user
        listing_ids = list(dict.fromkeys(request.listing_ids))
        if not listing_ids:
            listing_ids = [item.listing.id for item in self.get_cart(user_id=user_id).items]
        if not listing_ids:
            raise ValueError("Cart is empty")

        listings = [self.get_listing(listing_id) for listing_id in listing_ids]
        currencies = {listing.currency for listing in listings}
        if len(currencies) != 1:
            raise ValueError("A single order cannot mix currencies")
        currency = next(iter(currencies))
        total_minor = sum(listing.price_minor for listing in listings)
        order_id = f"order_{uuid4().hex[:16]}"
        now = utc_now()

        with self._connect() as db:
            db.execute(
                """
                INSERT INTO orders (
                    id, user_id, status, total_minor, currency, payment_provider,
                    created_at
                ) VALUES (?,?,?,?,?,?,?)
                """,
                (
                    order_id,
                    user_id,
                    StoreOrderStatus.PENDING.value,
                    total_minor,
                    currency,
                    request.payment_provider,
                    now,
                ),
            )
            for listing in listings:
                db.execute(
                    """
                    INSERT INTO order_items (
                        order_id, listing_id, asset_id, title, price_minor,
                        currency, license_type, asset_version
                    ) VALUES (?,?,?,?,?,?,?,?)
                    """,
                    (
                        order_id,
                        listing.id,
                        listing.asset_id,
                        listing.title,
                        listing.price_minor,
                        listing.currency,
                        listing.license_type.value,
                        listing.asset_version,
                    ),
                )

        provider = self.payments.get(request.payment_provider)
        payment = provider.charge(order_id=order_id, amount_minor=total_minor, currency=currency)
        if payment.status != "paid":
            return self.get_order(order_id, user_id=user_id)

        paid_at = utc_now()
        with self._connect() as db:
            db.execute(
                """
                UPDATE orders SET status=?, provider_reference=?, payment_metadata_json=?, paid_at=?
                WHERE id=?
                """,
                (
                    StoreOrderStatus.PAID.value,
                    payment.reference,
                    json.dumps(payment.metadata or {}, ensure_ascii=False),
                    paid_at,
                    order_id,
                ),
            )
            for listing in listings:
                entitlement_id = f"ent_{uuid4().hex[:16]}"
                db.execute(
                    """
                    INSERT OR IGNORE INTO entitlements (
                        id, user_id, order_id, listing_id, asset_id,
                        license_type, asset_version, granted_at
                    ) VALUES (?,?,?,?,?,?,?,?)
                    """,
                    (
                        entitlement_id,
                        user_id,
                        order_id,
                        listing.id,
                        listing.asset_id,
                        listing.license_type.value,
                        listing.asset_version,
                        paid_at,
                    ),
                )
            db.execute("DELETE FROM cart_items WHERE user_id=?", (user_id,))
        return self.get_order(order_id, user_id=user_id)

    def get_order(self, order_id: str, *, user_id: str | None = None) -> StoreOrder:
        user_id = user_id or self.local_user
        with self._connect() as db:
            row = db.execute("SELECT * FROM orders WHERE id=? AND user_id=?", (order_id, user_id)).fetchone()
            if row is None:
                raise StoreOrderNotFoundError(order_id)
            items = [
                StoreOrderItem(
                    listing_id=item["listing_id"],
                    asset_id=item["asset_id"],
                    title=item["title"],
                    price_minor=item["price_minor"],
                    currency=item["currency"],
                    license_type=StoreLicenseType(item["license_type"]),
                )
                for item in db.execute("SELECT * FROM order_items WHERE order_id=? ORDER BY rowid", (order_id,)).fetchall()
            ]
            entitlements = [self._entitlement_from_row(item) for item in db.execute(
                "SELECT * FROM entitlements WHERE order_id=? AND user_id=? ORDER BY granted_at",
                (order_id, user_id),
            ).fetchall()]
        return StoreOrder(
            id=row["id"],
            user_id=row["user_id"],
            status=StoreOrderStatus(row["status"]),
            total_minor=row["total_minor"],
            currency=row["currency"],
            payment_provider=row["payment_provider"],
            provider_reference=row["provider_reference"],
            items=items,
            entitlements=entitlements,
            created_at=row["created_at"],
            paid_at=row["paid_at"],
        )

    def list_orders(self, *, user_id: str | None = None) -> list[StoreOrder]:
        user_id = user_id or self.local_user
        with self._connect() as db:
            ids = [row["id"] for row in db.execute(
                "SELECT id FROM orders WHERE user_id=? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()]
        return [self.get_order(order_id, user_id=user_id) for order_id in ids]

    def list_entitlements(self, *, user_id: str | None = None) -> list[StoreEntitlement]:
        user_id = user_id or self.local_user
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM entitlements WHERE user_id=? ORDER BY granted_at DESC",
                (user_id,),
            ).fetchall()
        return [self._entitlement_from_row(row) for row in rows]

    def build_download(self, entitlement_id: str, *, user_id: str | None = None) -> tuple[Path, StoreDownloadRecord]:
        user_id = user_id or self.local_user
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM entitlements WHERE id=? AND user_id=?",
                (entitlement_id, user_id),
            ).fetchone()
            if row is None:
                raise StoreEntitlementNotFoundError(entitlement_id)
            entitlement = self._entitlement_from_row(row)
        asset = self.library.get(entitlement.asset_id)
        versions = {version.version: version for version in self.library.list_versions(asset.id)}
        version = versions.get(entitlement.asset_version)
        if version is None:
            raise ValueError("Purchased asset version is no longer indexed")

        archive_path = self.download_dir / f"{entitlement.id}.zip"
        metadata = {
            "entitlement_id": entitlement.id,
            "listing_id": entitlement.listing_id,
            "asset_id": entitlement.asset_id,
            "asset_version": entitlement.asset_version,
            "license_type": entitlement.license_type.value,
            "granted_at": entitlement.granted_at,
            "asset_name": asset.name,
            "category": asset.category,
            "tags": asset.tags,
            "provenance": asset.provenance,
        }
        license_text = self._license_text(entitlement.license_type, asset.name, entitlement.id)

        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            self._add_workspace_file(archive, version.image_path, "asset.png")
            if version.mask_path:
                self._add_workspace_file(archive, version.mask_path, "mask.png", required=False)
            if version.alpha_path:
                self._add_workspace_file(archive, version.alpha_path, "alpha.png", required=False)
            archive.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))
            archive.writestr("LICENSE.txt", license_text)

        record = StoreDownloadRecord(
            id=f"download_{uuid4().hex[:16]}",
            entitlement_id=entitlement.id,
            listing_id=entitlement.listing_id,
            asset_id=entitlement.asset_id,
            asset_version=entitlement.asset_version,
            downloaded_at=utc_now(),
        )
        with self._connect() as db:
            db.execute(
                "INSERT INTO downloads(id, entitlement_id, listing_id, asset_id, asset_version, downloaded_at) VALUES (?,?,?,?,?,?)",
                (
                    record.id,
                    record.entitlement_id,
                    record.listing_id,
                    record.asset_id,
                    record.asset_version,
                    record.downloaded_at,
                ),
            )
        return archive_path, record

    def stats(self) -> StoreStats:
        with self._connect() as db:
            listing = db.execute(
                """
                SELECT
                    SUM(CASE WHEN status='published' THEN 1 ELSE 0 END) AS published,
                    SUM(CASE WHEN status='published' AND price_minor=0 THEN 1 ELSE 0 END) AS free_count,
                    SUM(CASE WHEN status='published' AND price_minor>0 THEN 1 ELSE 0 END) AS paid_count
                FROM listings
                """
            ).fetchone()
            orders = db.execute(
                """
                SELECT COUNT(*) AS total,
                    SUM(CASE WHEN status='paid' THEN 1 ELSE 0 END) AS paid,
                    COALESCE(SUM(CASE WHEN status='paid' THEN total_minor ELSE 0 END),0) AS gross
                FROM orders
                """
            ).fetchone()
            entitlements = db.execute("SELECT COUNT(*) AS n FROM entitlements").fetchone()["n"]
            downloads = db.execute("SELECT COUNT(*) AS n FROM downloads").fetchone()["n"]
            currency_row = db.execute("SELECT currency FROM orders WHERE status='paid' ORDER BY paid_at DESC LIMIT 1").fetchone()
        return StoreStats(
            published_listings=int(listing["published"] or 0),
            free_listings=int(listing["free_count"] or 0),
            paid_listings=int(listing["paid_count"] or 0),
            orders=int(orders["total"] or 0),
            paid_orders=int(orders["paid"] or 0),
            entitlements=int(entitlements or 0),
            downloads=int(downloads or 0),
            gross_minor=int(orders["gross"] or 0),
            currency=currency_row["currency"] if currency_row else "CNY",
        )

    def _hydrate_listing(self, db: sqlite3.Connection, row: sqlite3.Row) -> StoreListing:
        asset = self.library.get(row["asset_id"])
        purchase_count = db.execute(
            "SELECT COUNT(*) AS n FROM entitlements WHERE listing_id=?",
            (row["id"],),
        ).fetchone()["n"]
        download_count = db.execute(
            "SELECT COUNT(*) AS n FROM downloads WHERE listing_id=?",
            (row["id"],),
        ).fetchone()["n"]
        return StoreListing(
            id=row["id"],
            asset_id=row["asset_id"],
            seller_id=row["seller_id"],
            seller_name=row["seller_name"],
            title=row["title"],
            description=row["description"],
            price_minor=row["price_minor"],
            currency=row["currency"],
            license_type=StoreLicenseType(row["license_type"]),
            status=StoreListingStatus(row["status"]),
            featured=bool(row["featured"]),
            preview_path=asset.image_path,
            category=asset.category,
            tags=asset.tags,
            asset_score=asset.asset_score,
            asset_version=asset.active_version,
            purchase_count=int(purchase_count or 0),
            download_count=int(download_count or 0),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _entitlement_from_row(row: sqlite3.Row) -> StoreEntitlement:
        return StoreEntitlement(
            id=row["id"],
            user_id=row["user_id"],
            order_id=row["order_id"],
            listing_id=row["listing_id"],
            asset_id=row["asset_id"],
            license_type=StoreLicenseType(row["license_type"]),
            asset_version=row["asset_version"],
            granted_at=row["granted_at"],
        )

    def _assert_publishable(self, review_state: str) -> None:
        if review_state not in self.PUBLISHABLE_STATES:
            raise ValueError(
                "Asset must be approved, production_ready, or in_use before it can be published to the store"
            )

    def _assert_currency_compatible_with_cart(self, user_id: str, currency: str) -> None:
        cart = self.get_cart(user_id=user_id)
        if cart.items and cart.currency != currency:
            raise ValueError("Cart cannot mix currencies")

    def _ensure_seller(self, seller_id: str, seller_name: str) -> None:
        now = utc_now()
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO sellers(id, display_name, created_at, updated_at)
                VALUES (?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET display_name=excluded.display_name, updated_at=excluded.updated_at
                """,
                (seller_id, seller_name.strip() or "Local Creator", now, now),
            )

    @staticmethod
    def _seller_id(name: str) -> str:
        clean = "".join(ch.lower() if ch.isalnum() else "_" for ch in name).strip("_")
        return f"seller_{clean[:32] or 'local_creator'}"

    def _add_workspace_file(self, archive: zipfile.ZipFile, relative_path: str, arcname: str, *, required: bool = True) -> None:
        path = (self.workspace / relative_path).resolve()
        workspace_root = self.workspace.resolve()
        if workspace_root not in path.parents and path != workspace_root:
            raise ValueError("Asset path escapes workspace")
        if not path.is_file():
            if required:
                raise ValueError(f"Store asset file is missing: {relative_path}")
            return
        archive.write(path, arcname=arcname)

    @staticmethod
    def _license_text(license_type: StoreLicenseType, asset_name: str, entitlement_id: str) -> str:
        common = (
            f"Game Creater Asset License\n\nAsset: {asset_name}\nEntitlement: {entitlement_id}\n"
            f"License tier: {license_type.value}\n\n"
            "You may use the asset in completed games and interactive media under the selected license tier.\n"
            "You may not resell, redistribute, sublicense, or publish the source asset itself as a competing asset pack.\n"
            "AI-generated or AI-completed portions may exist; provenance is included in metadata.json.\n"
        )
        if license_type == StoreLicenseType.PERSONAL:
            return common + "Commercial distribution is not permitted under the personal tier.\n"
        if license_type == StoreLicenseType.EXTENDED:
            return common + "Extended tier permits use across multiple commercial titles by the licensed buyer.\n"
        return common + "Commercial tier permits use in one or more commercial game projects by the licensed buyer.\n"
