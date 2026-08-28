# Asset Library Full Workflow

This workflow turns Asset Library into a complete 2D game-resource production and delivery surface:

```text
Image Import
-> Split
-> Hierarchy
-> Non-destructive Edit / Versions
-> Asset Pack
-> Generic / Godot 4 / Unity 2D delivery
```

Every operation is a typed `/api/v1/*` API operation. When the AI Native Control Layer is present, the same operations automatically appear in `/api/v1/ai/actions` and `/api/v1/ai/tools`.

## Image import

```text
POST /api/v1/library/import/image
```

Multipart fields:
- `image`: PNG/JPG/JPEG/WEBP
- `name`
- `category`
- `tags`: comma-separated

Imported assets receive a stable global Asset ID and three v1 resources:

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

Hierarchy is metadata only. It does not duplicate PNG files.

## Asset editing

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

The original version remains available in Asset Library history.

## Asset pack export

Create a pack:

```text
POST /api/v1/library/packs/export
```

Example:

```json
{
  "name": "forest_props",
  "asset_ids": ["asset_...", "asset_..."],
  "engine": "godot4",
  "include_masks": true,
  "include_alpha": true,
  "include_hierarchy": true
}
```

A Collection can be supplied through `collection_id` instead of or in addition to explicit asset IDs.

The response contains a pack id and an API download URL:

```text
GET /api/v1/library/packs/<pack_id>/download
```

Pack files are generated under the private local state directory:

```text
.game_creater_state/asset_packs/
```

They are not exposed through the static `/workspace` mount.

## Generic pack

Contains stable IDs, active versions, dimensions, category, tags, review state, provenance and optional parent/child relationships together with PNG/Mask/Alpha files.

## Godot 4 pack

Includes:

```text
godot4/
  assets/
    <asset_id>.png
  resources/
    <asset_id>.tres
  README.md
```

The `.tres` resources are native Godot 4 `AtlasTexture` resources referencing the exported PNGs.

## Unity 2D pack

Includes:

```text
unity2d/Assets/GameCreaterPack/
  assets/
  GameCreaterPack.json
  Editor/
    GameCreaterPackImporter.cs
```

After copying/importing the folder into a Unity project, run:

```text
Game Creater -> Configure Imported Asset Pack
```

The Editor tool configures textures as single Sprites with transparency, no mipmaps and 100 pixels per unit.

## Human UI

The web application exposes one **Asset Library Full Workflow** panel containing:
- image import
- split mode selection
- hierarchy inspection
- versioned editing
- batch-selected asset pack export

The existing Asset Library remains responsible for search, metadata, Collections, review state, version history and provenance.

## AI-native contract

The UI does not own any of the above business logic. All mutations go through typed backend operations. Therefore an agent can execute the same workflow without simulating mouse clicks:

```text
AI
-> import image
-> split
-> inspect hierarchy
-> edit selected child assets
-> create engine pack
-> download pack
```
