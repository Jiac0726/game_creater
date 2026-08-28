# Asset Pack System

This layer turns a loose export into a versioned, dependency-aware package workflow.

## Concepts

```text
Pack Draft
├─ Asset IDs
└─ Pack Dependencies
      ↓
Release 1.0.0
├─ frozen Asset Library versions
└─ pinned dependency versions
      ↓
Install
└─ lockfile
   ├─ pack versions
   └─ asset versions
```

Persistent pack metadata is stored in the Asset Library SQLite database. Export archives are generated under private `.game_creater_state/pack_exports`.

## Versioning

Releases require `MAJOR.MINOR.PATCH` semantic versions such as `1.0.0` or `2.3.1`.

A release freezes each member's active Asset Library version. Later edits to the same global Asset ID do not mutate old releases.

## Dependencies

Pack drafts can reference other Pack IDs. A dependency can request an exact version or leave it unspecified. At release time unspecified dependencies resolve to the latest existing release and are pinned into the immutable release manifest.

Dependency cycles are rejected before draft changes are committed.

## Install and lockfile

Installing a release recursively resolves dependency releases and writes a lock structure:

```json
{
  "schema": "game-creater/asset-pack-lock/v1",
  "root": {"pack_id": "pack_x", "version": "1.0.0"},
  "packs": {"pack_common": "1.2.0", "pack_x": "1.0.0"},
  "assets": {"asset_x": {"version": 3}}
}
```

Conflicting versions of the same dependent pack or global asset are rejected.

Uninstall removes the installation record only. It does not delete Asset Library source files.

## Updates

`GET /api/v1/library/package-system/updates` compares installed versions with the newest local releases. Updates are reported but never applied silently. The user or AI must explicitly install the newer version.

## API

```text
GET    /api/v1/library/package-system/packs
POST   /api/v1/library/package-system/packs
GET    /api/v1/library/package-system/packs/{pack_id}
PATCH  /api/v1/library/package-system/packs/{pack_id}
GET    /api/v1/library/package-system/packs/{pack_id}/releases
POST   /api/v1/library/package-system/packs/{pack_id}/releases
POST   /api/v1/library/package-system/packs/{pack_id}/install
DELETE /api/v1/library/package-system/packs/{pack_id}/install
GET    /api/v1/library/package-system/installed
GET    /api/v1/library/package-system/updates
POST   /api/v1/library/package-system/packs/{pack_id}/export
GET    /api/v1/library/package-system/exports/{export_id}
```

## Export

A released package ZIP contains:

```text
pack.json
assets/
  asset_<id>/
    asset.png
    mask.png
    alpha.png
    asset.json
```

`pack.json` contains both current pack metadata and the immutable selected release snapshot.

## Human UI / AI

The Pack Manager can create packs from selected Asset Library items, release semantic versions, install/uninstall, inspect update availability and export a frozen package.

All operations are typed `/api/v1/*` actions and are automatically discoverable by the AI Native Control Layer. Destructive-looking actions such as uninstall remain confirmation-gated by the AI policy; source assets are never removed by pack uninstall.
