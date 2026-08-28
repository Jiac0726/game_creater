# Asset Store

Game Creater's Asset Store sits on top of the global Asset Library. It does not duplicate source assets when a creator publishes a product.

```text
Asset Library
  -> review / production readiness
  -> Store Listing
  -> Storefront / search
  -> Cart
  -> Checkout Provider
  -> Order snapshot
  -> Entitlement
  -> Version-locked download ZIP
```

## Current scope

The first implementation is a **local marketplace MVP**. It validates commerce-domain behavior without pretending to collect real money.

Implemented:

- publish an Asset Library item as a product
- Draft / Published / Archived listing states
- Personal / Commercial / Extended license tiers
- free and paid prices
- category, tags, score, seller and asset-version information on product cards
- storefront search/filtering
- cart
- checkout provider abstraction
- explicit Mock checkout provider for local development
- order records
- immutable order-item asset-version snapshots
- entitlement records
- purchased-asset library
- entitlement-gated ZIP downloads
- download records and basic sales/download statistics
- creator listing console

Not implemented as real production commerce yet:

- user authentication / accounts
- real payment processor
- refunds / disputes / tax / invoices
- creator onboarding / identity / payouts
- revenue sharing
- moderation and abuse handling
- remote object storage / CDN / signed URLs
- multi-tenant authorization

Do not expose the current localhost FastAPI development server as a public marketplace.

## Publishing rule

An AI-generated asset cannot silently become a public product.

Only Asset Library items in one of these review states may be Published:

```text
approved
production_ready
in_use
```

`needs_review` and `archived` assets can only remain Draft until their library review state changes.

This keeps the pipeline explicit:

```text
AI generation / segmentation
-> needs_review
-> human / QA approval
-> production_ready
-> store publication
```

## Store state

Commerce state is deliberately kept outside the static `/workspace` mount:

```text
.game_creater_state/
  store.db
  downloads/
```

Asset image/mask binaries stay in their Scene / Asset Library paths. Store listings reference the stable global `library_asset_id`.

Core tables:

```text
sellers
listings
cart_items
orders
order_items
entitlements
downloads
```

## Version locking

The product page shows the current active Asset Library version. Checkout copies that version number into `order_items` and `entitlements`.

Example:

```text
Purchase time:
asset_xxx -> active version v2

Later creator work:
asset_xxx -> active version v3

Existing entitlement:
still points to v2
```

The downloader resolves the purchased version from Asset Library version history. A later refinement therefore does not silently mutate an already purchased source package.

## Entitlements

A download is not authorized merely because a listing is public or free.

Both free and paid products go through checkout and create an Entitlement:

```text
ent_xxx
  user_id
  order_id
  listing_id
  asset_id
  license_type
  asset_version
  granted_at
```

The download API requires the entitlement id for the current local user.

## Download package

The generated ZIP contains, when available:

```text
asset.png
mask.png
alpha.png
metadata.json
LICENSE.txt
```

`metadata.json` includes:

- entitlement id
- listing id
- global asset id
- purchased asset version
- license tier
- asset name/category/tags
- Asset Library provenance

The original Scene / Project provenance is preserved so AI-generated or AI-completed source history remains inspectable.

## License tiers

Current MVP tiers:

### Personal

Non-commercial use. Source asset redistribution is prohibited.

### Commercial

Commercial game-project use by the licensed buyer. Source asset redistribution or resale as a competing asset product is prohibited.

### Extended

Intended for broader commercial reuse across multiple titles by the licensed buyer. Source redistribution remains prohibited.

These text licenses are MVP product terms, not jurisdiction-specific legal advice. Before a public launch they should be replaced with reviewed legal terms, refund rules and marketplace policies.

## Payment providers

Payment is isolated behind `StorePaymentProvider`.

Current provider:

```text
mock
```

Mock checkout:

- makes no external request
- never charges real money
- clearly records `payment_provider=mock`
- returns a `mock_*` provider reference
- is intended only for local workflow validation

Paid Mock checkout can be disabled:

```bash
export GAME_CREATER_ALLOW_MOCK_PAID=0
```

A production provider should implement the same boundary but should not directly grant entitlements from an unverified client-side callback. The final entitlement should be created only after server-side payment verification / webhook confirmation.

## API

Catalog:

```text
GET /api/v1/store/stats
GET /api/v1/store/listings
GET /api/v1/store/listings/<listing_id>
GET /api/v1/store/payment/providers
```

Creator:

```text
GET   /api/v1/store/seller/listings
POST  /api/v1/store/seller/listings
PATCH /api/v1/store/seller/listings/<listing_id>
```

Cart and checkout:

```text
GET    /api/v1/store/cart
POST   /api/v1/store/cart/<listing_id>
DELETE /api/v1/store/cart/<listing_id>
POST   /api/v1/store/checkout
```

Purchases:

```text
GET /api/v1/store/orders
GET /api/v1/store/orders/<order_id>
GET /api/v1/store/library
GET /api/v1/store/downloads/<entitlement_id>
```

## Example: publish

```json
POST /api/v1/store/seller/listings
{
  "asset_id": "asset_1234567890abcdef",
  "title": "Ancient Mossy Tree",
  "description": "Transparent 2D environment prop",
  "price_minor": 990,
  "currency": "CNY",
  "license_type": "commercial",
  "seller_name": "Local Creator",
  "publish": true,
  "featured": false
}
```

## Example: checkout

Using cart contents:

```json
POST /api/v1/store/checkout
{
  "listing_ids": [],
  "payment_provider": "mock"
}
```

Or direct checkout:

```json
{
  "listing_ids": ["listing_xxx"],
  "payment_provider": "mock"
}
```

## Production roadmap

Recommended next sequence before any public launch:

```text
1. User / creator identity and RBAC
2. private store DB migrations
3. object storage + immutable release artifacts
4. real payment provider adapter
5. webhook-confirmed entitlement grant
6. creator payout ledger
7. license / refund / tax / moderation policy
8. signed download URLs + rate limits
9. store search / recommendation embeddings
10. packs / bundles / discount campaigns
```
