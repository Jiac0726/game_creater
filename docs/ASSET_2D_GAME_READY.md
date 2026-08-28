# 2D Game Ready Resources

PR #3 extends Asset Library from reusable PNG management into engine-ready 2D resource delivery.

```text
Asset Library
├─ Polygon Collision
├─ Sprite Animation / Frame Workbench
├─ TileSet / Terrain / Autotile
└─ Game Ready Pack
   ├─ Generic
   ├─ Godot 4
   └─ Unity 2D
```

All operations are typed `/api/v1/*` APIs and are automatically exposed by the AI Native Control Layer.

## Polygon Collision

Runtime config supports `collision_mode: polygon`.

Generate an initial polygon from the active Mask / Alpha:

```text
POST /api/v1/library/assets/<asset_id>/collision-polygon/generate
```

The automatic generator deliberately uses a dependency-free convex hull. It is intended as a stable first pass, not as a perfect concave outline.

Read or manually/AI edit normalized points:

```text
GET   /api/v1/library/assets/<asset_id>/collision-polygon
PATCH /api/v1/library/assets/<asset_id>/collision-polygon
```

Points use normalized image coordinates (`0..1`). Godot export converts them to `CollisionPolygon2D`; Unity export converts them to local Sprite units and calls `PolygonCollider2D.SetPath`.

## Sprite Animation and frame sequencing

Create an animation from ordered Library Asset IDs:

```text
POST /api/v1/library/animations
```

```json
{
  "name": "walk",
  "frame_asset_ids": ["asset_a", "asset_b", "asset_c"],
  "fps": 8,
  "loop": true
}
```

Frame order is preserved and duplicate frame IDs are valid.

The dedicated frame-sequence operation is:

```text
PUT /api/v1/library/animations/<animation_id>/frames
```

Strict reorder example:

```json
{
  "frame_asset_ids": ["asset_c", "asset_a", "asset_b"],
  "require_same_frames": true
}
```

With `require_same_frames=true`, the backend compares the frame multiset and rejects accidental frame additions/removals. Set it to `false` when intentionally duplicating or deleting a frame.

The Human UI provides a frame workbench with drag reorder, up/down movement, duplicate and remove operations.

### Godot 4

Game Ready Pack generates `godot4/animations/<animation_id>.tscn` containing native `AnimatedSprite2D` and embedded `SpriteFrames`.

### Unity 2D

The generated Editor builder creates native `.anim` files through `AnimationClip` and `AnimationUtility.SetObjectReferenceCurve`, targeting `SpriteRenderer.m_Sprite`.

## TileSet, Terrain and Autotile

Create a TileSet definition:

```text
POST /api/v1/library/tilesets
```

Basic fields remain `tile_asset_ids`, tile width/height and terrain tags. Autotile adds:

```json
{
  "autotile_mode": "cardinal4",
  "terrain_rules": [
    {
      "asset_id": "asset_grass_isolated",
      "terrain": "grass",
      "neighbor_mask": 0,
      "priority": 0
    },
    {
      "asset_id": "asset_grass_full",
      "terrain": "grass",
      "neighbor_mask": 85,
      "priority": 10
    }
  ]
}
```

Modes:

```text
none
cardinal4
eight8
```

Neighbor bits are stable and engine-independent:

```text
N  = 1
NE = 2
E  = 4
SE = 8
S  = 16
SW = 32
W  = 64
NW = 128
```

For `cardinal4`, only N/E/S/W bits are accepted; a fully connected cardinal tile is `1 + 4 + 16 + 64 = 85`. `eight8` accepts `0..255`.

Each Tile asset can have one rule containing terrain, mask and priority. Priority resolves multiple candidates within the same terrain in the generated engine resource.

### Godot 4 terrain delivery

The generated EditorScript builds a native `TileSet` with `TileSetAtlasSource`. When terrain rules exist it also creates a terrain set, chooses `TERRAIN_MODE_MATCH_SIDES` for `cardinal4` or `TERRAIN_MODE_MATCH_CORNERS_AND_SIDES` for `eight8`, assigns each tile's `TileData.terrain_set/terrain`, and writes terrain peering bits. The resulting `.tres` is designed for Godot 4 `TileMapLayer` terrain painting / `set_cells_terrain_connect()` workflows.

### Unity 2D autotile delivery

Game Ready Pack remains self-contained and does not require the optional 2D Tilemap Extras `RuleTile`. It generates `Runtime/GameCreaterAutoTile.cs`, a native `TileBase` implementation using `RefreshTile` and `GetTileData`, plus Editor-created AutoTile assets grouped by terrain.

Normal `UnityEngine.Tilemaps.Tile` assets are still generated alongside AutoTiles.

## Game Ready Pack

```text
POST /api/v1/library/packs/export-game-ready
```

Animation frames and TileSet assets are automatically included in the dependency set even when omitted from `asset_ids`.

The pack freezes:

```text
manifest.json
runtime_config.json
game_ready_2d.json
```

`game_ready_2d.json` schema v2 includes collision polygons, animation definitions and TileSet terrain/autotile rules.

## Human UI

The **2D Game Ready Resources** panel supports:

- Polygon Collision generation
- Sprite Animation creation
- animation selection and drag frame reordering
- frame duplicate/remove
- TileSet creation
- `cardinal4` / `eight8` Autotile mode
- Terrain Rule templates and bitmask editing
- Godot / Unity / Generic Game Ready export

## AI-native operations

Important actions exposed through `/api/v1/ai/tools` include:

```text
post.library.assets.asset_id.collision.polygon.generate
patch.library.assets.asset_id.collision.polygon
post.library.animations
patch.library.animations.clip_id
put.library.animations.clip_id.frames
post.library.tilesets
patch.library.tilesets.tileset_id
post.library.packs.export.game.ready
```

The TileSet schemas expose `autotile_mode` and typed `terrain_rules`, so AI agents do not need to encode undocumented strings.

## Real engine validation

Core CI validates Python persistence, package structure, generated source/text syntax, frontend JavaScript and AI schemas. It does not install heavyweight proprietary/game editors.

For a real local Godot 4 validation:

```bash
python scripts/validate_godot_game_ready.py path/to/godot_pack.zip --godot godot
```

The validator creates a temporary project and uses the real Godot binary for `--import`, `--check-only` on generated TileSet scripts, and resource `load()` checks.

For a real local Unity validation:

```bash
python scripts/validate_unity_game_ready.py path/to/unity_pack.zip --unity "C:/Program Files/Unity/Hub/Editor/<version>/Editor/Unity.exe"
```

The validator creates a real empty Unity project in batch mode, copies the pack into `Assets/GameCreaterPack`, executes `GameCreaterGameReady2DBuilder.Build`, and verifies generated Prefab/Animation/Tile folders. A valid local Unity Editor installation/license is required.

These scripts make the external validation boundary executable rather than leaving it as a manual checklist.
