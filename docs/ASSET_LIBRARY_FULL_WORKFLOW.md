# Asset Library Full Workflow

This workflow turns Asset Library into a complete 2D game-resource production, management and engine-delivery surface:

```text
Image Import
-> Split
-> Hierarchy
-> Non-destructive Edit / Versions
-> Runtime Config
-> Polygon Collision / Sprite Animation / TileSet
-> Preflight
-> Asset Pack
-> Generic / Godot 4 / Unity 2D delivery
```

Every operation is a typed `/api/v1/*` API operation. With the AI Native Control Layer, the same operations automatically appear in `/api/v1/ai/actions` and `/api/v1/ai/tools`.

## Image import

Single image:

```text
POST /api/v1/library/import/image
```

Batch image import, up to 200 files:

```text
POST /api/v1/library/import/images
```

Supported files: PNG/JPG/JPEG/WEBP. Imported assets receive a stable global Asset ID and versioned Image / Mask / Alpha resources.

## Split

```text
POST /api/v1/library/assets/<asset_id>/split
```

Modes:
- `grid` for sprite sheets and atlases
- `alpha_components` for separated transparent sprites
- `ai_scene` using GroundingDINO + SAM2

Split results become normal Library assets and are linked under the source asset.

## Hierarchy

```text
GET    /api/v1/library/assets/<asset_id>/hierarchy
POST   /api/v1/library/assets/<asset_id>/children
DELETE /api/v1/library/assets/<asset_id>/children/<child_asset_id>
POST   /api/v1/library/assets/<parent_asset_id>/reparent
```

Hierarchy uses `parent_of` / `part_of` relations, never duplicates PNG files and rejects cycles when reparenting.

## Asset editing and versions

```text
POST /api/v1/library/assets/<asset_id>/edit
POST /api/v1/library/assets/bulk/edit
POST /api/v1/library/assets/<asset_id>/versions/<version>/activate
```

Supported non-destructive edits:
- crop
- resize
- trim transparent border
- horizontal / vertical flip
- rotate 90 degrees
- transparent padding

Image, Mask and Alpha are transformed together and every edit creates a new Library version. Activating an older version does not delete later versions.

## Runtime configuration

```text
GET   /api/v1/library/assets/<asset_id>/runtime-config
PATCH /api/v1/library/assets/<asset_id>/runtime-config
POST  /api/v1/library/assets/bulk/runtime-config
```

Game-facing fields include Pivot, Pixels Per Unit, render layer, sorting order, collision mode (`none`, `box`, `polygon`), Trigger/Area and gameplay tags.

See `docs/ASSET_RUNTIME_CONFIG.md`.

## Polygon Collision

Generate an initial polygon from the active Mask / Alpha:

```text
POST /api/v1/library/assets/<asset_id>/collision-polygon/generate
```

Read or edit normalized polygon points:

```text
GET   /api/v1/library/assets/<asset_id>/collision-polygon
PATCH /api/v1/library/assets/<asset_id>/collision-polygon
```

The automatic generator uses a dependency-free Mask convex hull as a stable first pass. Complex concave shapes can be edited later by a human or AI agent.

## Sprite Animation

```text
GET/POST /api/v1/library/animations
GET/PATCH /api/v1/library/animations/<animation_id>
```

Animation clips preserve ordered Asset ID frames, FPS and loop state. Duplicate frame IDs are allowed intentionally.

## TileSet

```text
GET/POST /api/v1/library/tilesets
GET/PATCH /api/v1/library/tilesets/<tileset_id>
```

TileSet definitions preserve the selected Asset IDs, tile width/height and terrain tags.

See `docs/ASSET_2D_GAME_READY.md` for Polygon, Animation and TileSet engine mappings.

## Export Preflight

```text
POST /api/v1/library/packs/preflight
```

Checks include:
- missing or unreadable active image
- metadata/image dimension mismatch
- missing Mask / Alpha when required
- Mask / Alpha size mismatch
- review status
- uncategorized assets
- invalid active version

Errors and warnings are returned separately.

## Asset pack export

Base pack:

```text
POST /api/v1/library/packs/export
```

Runtime-aware pack:

```text
POST /api/v1/library/packs/export-runtime
```

Game Ready pack:

```text
POST /api/v1/library/packs/export-game-ready
```

Download:

```text
GET /api/v1/library/packs/<pack_id>/download
```

Animation frames and TileSet dependencies are automatically added to Game Ready exports even when not manually included in `asset_ids`.

Game Ready export freezes:

```text
manifest.json
runtime_config.json
game_ready_2d.json
```

Pack files are generated under the private local state directory:

```text
.game_creater_state/asset_packs/
```

## Godot 4 delivery

Depending on export level, a package can contain:

```text
godot4/
  assets/
  resources/          # AtlasTexture .tres
  prefabs/            # Sprite2D + runtime/collision .tscn
  animations/         # AnimatedSprite2D + SpriteFrames .tscn
  tilesets/           # TileSet EditorScript + definition
```

Polygon Collision is serialized as native flat-number `PackedVector2Array`. TileSet EditorScripts create native `.tres` resources using Godot 4 `TileSet` + `TileSetAtlasSource`.

## Unity 2D delivery

Depending on export level, a package can contain:

```text
Assets/GameCreaterPack/
  assets/
  Prefabs/
  Animations/
  Tiles/
  Runtime/
  Editor/
```

Generated Editor tooling configures Sprites and runtime Prefabs, then can generate `PolygonCollider2D`, native `AnimationClip` `.anim` files and `UnityEngine.Tilemaps.Tile` assets.

## Human UI

The application now exposes:
- Asset Library Full Workflow
- Advanced Asset Workflow
- Runtime Config
- 2D Game Ready Resources

Together they cover import, split, hierarchy, versions, editing, collision, animation, TileSet, Preflight and engine delivery.

## AI-native contract

The UI owns no unique business logic. Every mutation goes through typed backend APIs, so an AI agent can perform the same operations without simulating mouse clicks.
