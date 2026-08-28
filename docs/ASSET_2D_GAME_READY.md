# 2D Game Ready Resources

PR #3 extends Asset Library from reusable PNG management into engine-ready 2D resource delivery.

```text
Asset Library
├─ Polygon Collision
├─ Sprite Animation
├─ TileSet
└─ Game Ready Pack
   ├─ Generic
   ├─ Godot 4
   └─ Unity 2D
```

All operations are typed `/api/v1/*` APIs and are automatically exposed by the AI Native Control Layer.

## Polygon Collision

Runtime config now supports:

```json
{
  "collision_mode": "polygon"
}
```

Generate an initial polygon from the active Mask / Alpha:

```text
POST /api/v1/library/assets/<asset_id>/collision-polygon/generate
```

Example:

```json
{
  "alpha_threshold": 1,
  "max_points": 24
}
```

The automatic generator deliberately uses a dependency-free convex hull. It is intended as a stable first pass, not as a perfect concave outline.

Read or manually/AI edit the normalized points:

```text
GET   /api/v1/library/assets/<asset_id>/collision-polygon
PATCH /api/v1/library/assets/<asset_id>/collision-polygon
```

Points use normalized image coordinates (`0..1`) so the same polygon can be converted into different engine coordinate systems.

Godot game-ready export converts the normalized polygon into native `CollisionPolygon2D` coordinates and writes the flat-number `PackedVector2Array(...)` representation expected by `.tscn` text resources.

Unity game-ready export converts the same points into local Sprite units and calls `PolygonCollider2D.SetPath` in the generated Editor builder.

## Sprite Animation

Create an animation clip from ordered Library Asset IDs:

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

Frame order is preserved and duplicate frame IDs are allowed intentionally.

APIs:

```text
GET   /api/v1/library/animations
POST  /api/v1/library/animations
GET   /api/v1/library/animations/<animation_id>
PATCH /api/v1/library/animations/<animation_id>
```

### Godot 4

Game Ready Pack generates:

```text
godot4/animations/<animation_id>.tscn
```

The scene contains a native `AnimatedSprite2D` and embedded `SpriteFrames` resource using the exported frame textures.

### Unity 2D

The generated `GameCreaterGameReady2DBuilder.cs` creates native `.anim` files through `AnimationClip` and `AnimationUtility.SetObjectReferenceCurve`, targeting `SpriteRenderer.m_Sprite`.

## TileSet

Create a TileSet definition from Library Assets:

```text
POST /api/v1/library/tilesets
```

```json
{
  "name": "forest_ground",
  "tile_asset_ids": ["asset_grass", "asset_dirt", "asset_edge"],
  "tile_width": 32,
  "tile_height": 32,
  "terrain_tags": ["ground", "grass"]
}
```

APIs:

```text
GET   /api/v1/library/tilesets
POST  /api/v1/library/tilesets
GET   /api/v1/library/tilesets/<tileset_id>
PATCH /api/v1/library/tilesets/<tileset_id>
```

### Godot 4

Game Ready Pack contains:

```text
godot4/tilesets/
  build_<tileset_id>.gd
  <tileset_id>.json
```

Run the generated `EditorScript` once in the Godot editor. It creates a native `TileSet` resource using `TileSetAtlasSource` and saves:

```text
godot4/tilesets/<tileset_id>.tres
```

This follows Godot 4's `TileSet` / `TileMapLayer` model rather than the deprecated `TileMap` workflow.

### Unity 2D

The generated Editor builder creates native `UnityEngine.Tilemaps.Tile` assets under:

```text
Assets/GameCreaterPack/Tiles/<tileset_id>/
```

Each Tile references its imported Sprite and uses Sprite collision by default.

## Game Ready Pack

```text
POST /api/v1/library/packs/export-game-ready
```

Example:

```json
{
  "name": "forest_game_ready",
  "asset_ids": ["asset_tree"],
  "animation_ids": ["anim_walk"],
  "tileset_ids": ["tileset_ground"],
  "engine": "godot4",
  "include_runtime_config": true,
  "include_collision_polygons": true
}
```

Animation frames and TileSet assets are automatically added to the exported asset dependency set even when they were not explicitly listed in `asset_ids`.

The pack freezes:

```text
manifest.json
runtime_config.json
game_ready_2d.json
```

so asset versions, runtime settings, collision polygons, animation definitions and TileSet definitions remain reproducible.

## Human UI

The **2D Game Ready Resources** panel supports:

- generate Polygon Collision from current asset Mask
- choose solid vs Trigger collision
- create animation from selected Library assets
- set FPS / loop
- create TileSet from selected Library assets
- set tile size / terrain tags
- export Godot / Unity / Generic Game Ready Pack

## AI-native operations

Examples available automatically through `/api/v1/ai/tools`:

```text
post.library.assets.asset_id.collision.polygon.generate
patch.library.assets.asset_id.collision.polygon
post.library.animations
patch.library.animations.clip_id
post.library.tilesets
patch.library.tilesets.tileset_id
post.library.packs.export.game.ready
```

An AI agent can therefore generate/adjust collision geometry, assemble animation frames, group tiles and deliver an engine package without simulating UI clicks.

## Validation boundary

CI validates the Python data model, persistence, dependency expansion, exported package contents, Godot text serialization rules used here, Unity builder source generation, frontend JavaScript syntax and AI action schemas.

Actual Godot Editor import and Unity Editor C# compilation still require target-machine integration tests; CI does not claim those external engine runs have already happened.
