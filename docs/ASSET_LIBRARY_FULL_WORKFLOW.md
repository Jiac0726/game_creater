# Asset Library Full Workflow

This workflow turns Asset Library into a complete 2D game-resource production, management and engine-delivery surface:

```text
Image Import
-> Split
-> Hierarchy
-> Non-destructive Edit / Versions
-> Runtime Config
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

Supported files: PNG/JPG/JPEG/WEBP. Imported assets receive a stable global Asset ID and three v1 resources:

```text
library_imports/<asset_id>/
  source.png
  mask.png
  alpha.png
```

The initial Library version is `imported`; provenance records the original filename and import timestamp.

## Split

```text
POST /api/v1/library/assets/<asset_id>/split
```

### Grid

Use for sprite sheets and regular atlases:

```json
{
  "mode": "grid",
  "rows": 2,
  "columns": 4
}
```

### Alpha components

Use when individual sprites are separated by transparent pixels:

```json
{
  "mode": "alpha_components",
  "min_area": 64
}
```

### AI scene split

Reuse GroundingDINO + SAM2:

```json
{
  "mode": "ai_scene",
  "prompts": ["tree", "wooden crate", "rock"]
}
```

AI scene split produces a normal Scene and normal Asset Library entries; the generated Library assets are linked under the imported parent.

## Hierarchy

Split children are automatically represented as:

```text
Parent
  parent_of -> Child

Child
  part_of -> Parent
```

Read recursively:

```text
GET /api/v1/library/assets/<asset_id>/hierarchy
```

Manual membership:

```text
POST /api/v1/library/assets/<asset_id>/children
DELETE /api/v1/library/assets/<asset_id>/children/<child_asset_id>
```

Bulk reparenting:

```text
POST /api/v1/library/assets/<parent_asset_id>/reparent
```

Reparenting can remove previous parent links and rejects hierarchy cycles. Hierarchy is metadata only and never duplicates PNG files.

## Asset editing and versions

```text
POST /api/v1/library/assets/<asset_id>/edit
```

Current operations:
- `crop`
- `resize`
- `trim_alpha`
- `flip_horizontal`
- `flip_vertical`
- `rotate_90`
- `pad`

Batch editing:

```text
POST /api/v1/library/assets/bulk/edit
```

Editing is non-destructive:

```text
v1 imported / segmented
-> v2 edit:trim_alpha
-> v3 edit:resize
```

Image, mask and alpha are transformed together and stored under:

```text
library_versions/<asset_id>/
```

Switch the active version without deleting newer versions:

```text
POST /api/v1/library/assets/<asset_id>/versions/<version>/activate
```

This enables rollback while preserving the complete edit history.

## Runtime configuration

Each Library asset can carry game-facing configuration independently from its image version:

```text
GET   /api/v1/library/assets/<asset_id>/runtime-config
PATCH /api/v1/library/assets/<asset_id>/runtime-config
POST  /api/v1/library/assets/bulk/runtime-config
```

Runtime fields:
- pivot X / Y
- Pixels Per Unit
- render layer
- sorting order
- collision mode (`none` / `box`)
- trigger / area flag
- gameplay tags

See `docs/ASSET_RUNTIME_CONFIG.md` for the full engine-delivery contract.

## Export Preflight

Validate selected assets before creating a production pack:

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

The result separates errors and warnings. Human UI and AI agents can use the same report before export.

## Asset pack export

Base pack:

```text
POST /api/v1/library/packs/export
```

Runtime-aware pack:

```text
POST /api/v1/library/packs/export-runtime
```

Example:

```json
{
  "name": "forest_props",
  "asset_ids": ["asset_...", "asset_..."],
  "engine": "godot4",
  "include_masks": true,
  "include_alpha": true,
  "include_hierarchy": true,
  "include_runtime_config": true
}
```

A Collection can be supplied through `collection_id` instead of or in addition to explicit asset IDs.

Download:

```text
GET /api/v1/library/packs/<pack_id>/download
```

Pack files are generated under the private local state directory:

```text
.game_creater_state/asset_packs/
```

They are not exposed through the static `/workspace` mount.

## Generic pack

Contains stable IDs, active versions, dimensions, category, tags, review state, provenance and optional parent/child relationships together with PNG/Mask/Alpha files. Runtime-aware packs additionally include `runtime_config.json`.

## Godot 4 pack

Base files:

```text
godot4/
  assets/
  resources/
    <asset_id>.tres
```

Runtime-aware delivery adds:

```text
godot4/
  prefabs/
    <asset_id>.tscn
  RUNTIME_IMPORT.md
```

Generated `.tscn` assets contain Sprite2D pivot offset, z-index and optional `StaticBody2D` or `Area2D` box collision.

## Unity 2D pack

Base files:

```text
unity2d/Assets/GameCreaterPack/
  assets/
  GameCreaterPack.json
  Editor/
    GameCreaterPackImporter.cs
```

Runtime-aware delivery adds:

```text
runtime_config.json
Runtime/GameCreaterRuntimeMetadata.cs
Editor/GameCreaterRuntimePrefabBuilder.cs
```

Run:

```text
Game Creater -> Build Runtime Asset Prefabs
```

The Unity Editor builder sets Sprite pivot, PPU and sorting order, creates optional `BoxCollider2D`, applies trigger state and writes Prefabs with Game Creater runtime metadata.

## Human UI

The web application exposes one Asset Library workflow containing:
- single and batch image import
- split mode selection
- hierarchy inspection and reparenting
- versioned editing and rollback
- batch non-destructive edits
- runtime configuration
- pack Preflight
- Generic / Godot / Unity pack export

The existing Asset Library remains responsible for search, metadata, Collections, review state, version history and provenance.

## AI-native contract

The UI does not own any business logic. All operations go through typed backend actions, so an agent can perform the same workflow without simulating mouse clicks:

```text
AI
-> batch import
-> split
-> assign hierarchy
-> edit / rollback versions
-> configure pivot / PPU / layer / collision
-> run Preflight
-> create runtime-aware engine pack
-> download pack
```
