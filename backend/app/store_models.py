from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class StoreLicenseType(str, Enum):
    PERSONAL = "personal"
    COMMERCIAL = "commercial"
    EXTENDED = "extended"


class StoreListingStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class StoreOrderStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class StoreListingCreate(BaseModel):
    asset_id: str
    title: Optional[str] = None
    description: str = ""
    price_minor: int = Field(default=0, ge=0)
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    license_type: StoreLicenseType = StoreLicenseType.COMMERCIAL
    seller_name: str = "Local Creator"
    publish: bool = True
    featured: bool = False


class StoreListingPatch(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    price_minor: Optional[int] = Field(default=None, ge=0)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    license_type: Optional[StoreLicenseType] = None
    status: Optional[StoreListingStatus] = None
    featured: Optional[bool] = None


class StoreListing(BaseModel):
    id: str
    asset_id: str
    seller_id: str
    seller_name: str
    title: str
    description: str = ""
    price_minor: int = 0
    currency: str = "CNY"
    license_type: StoreLicenseType = StoreLicenseType.COMMERCIAL
    status: StoreListingStatus = StoreListingStatus.DRAFT
    featured: bool = False
    preview_path: str
    category: str = "uncategorized"
    tags: list[str] = Field(default_factory=list)
    asset_score: float = 0.0
    asset_version: int = 1
    download_count: int = 0
    purchase_count: int = 0
    created_at: str
    updated_at: str


class StoreSearchResult(BaseModel):
    items: list[StoreListing]
    total: int
    limit: int
    offset: int


class StoreCartItem(BaseModel):
    listing: StoreListing
    added_at: str


class StoreCart(BaseModel):
    user_id: str
    items: list[StoreCartItem] = Field(default_factory=list)
    total_minor: int = 0
    currency: str = "CNY"


class StoreCheckoutRequest(BaseModel):
    listing_ids: list[str] = Field(default_factory=list)
    payment_provider: str = "mock"


class StoreOrderItem(BaseModel):
    listing_id: str
    asset_id: str
    title: str
    price_minor: int
    currency: str
    license_type: StoreLicenseType
    asset_version: int


class StoreEntitlement(BaseModel):
    id: str
    user_id: str
    order_id: str
    listing_id: str
    asset_id: str
    license_type: StoreLicenseType
    asset_version: int
    granted_at: str


class StoreOrder(BaseModel):
    id: str
    user_id: str
    status: StoreOrderStatus
    total_minor: int
    currency: str
    payment_provider: str
    provider_reference: Optional[str] = None
    items: list[StoreOrderItem] = Field(default_factory=list)
    entitlements: list[StoreEntitlement] = Field(default_factory=list)
    created_at: str
    paid_at: Optional[str] = None


class StoreDownloadRecord(BaseModel):
    id: str
    entitlement_id: str
    listing_id: str
    asset_id: str
    asset_version: int
    downloaded_at: str


class StoreStats(BaseModel):
    published_listings: int = 0
    free_listings: int = 0
    paid_listings: int = 0
    orders: int = 0
    paid_orders: int = 0
    entitlements: int = 0
    downloads: int = 0
    gross_minor: int = 0
    currency: str = "CNY"
