# Asset Runtime Config

Game Creater treats a reusable 2D game asset as more than a PNG. Each Library asset can now carry engine-facing runtime configuration:

```text
Asset
├─ Image / Mask / Alpha
├─ Versions
├─ Hierarchy
└─ Runtime Config
   ├─ Pivot X / Y
   ├─ Pixels Per Unit
   ├─ Render Layer
   ├─ Sorting Order
   ├─ Collision Mode
   ├─ Trigger / Area
   └─ Gameplay Tags
```

The runtime configuration is stored in the same local Asset Library SQLite database through the `asset_runtime_config` table. It is separate from image versions: switching an image version does not silently overwrite gameplay configuration.

Collision modes now include:

```text
none
box
polygon
```

Polygon point data is stored separately so image-version/runtime metadata and editable collision geometry do not overwrite each other. See `docs/ASSET_2D_GAME_READY.md` for Polygon Collision, Sprite Animation and TileSet delivery.

## API

Read config:

```text
GET /api/v1/library/assets/<asset_id>/runtime-config
```

Update config:

```text
PATCH /api/v1/library/assets/<asset_id>/runtime-config
```

Example:

```json
{
  "pivot_x": 0.5,
  "pivot_y": 1.0,
  "pixels_per_unit": 100,
  "render_layer": "foreground_props",
  "sorting_order": 20,
  "collision_mode": "box",
  "collision_is_trigger": false,
  "gameplay_tags": ["obstacle", "destructible"]
}
```

Batch apply the same runtime config:

```text
POST /api/v1/library/assets/bulk/runtime-config
```

Runtime-aware pack export:

```text
POST /api/v1/library/packs/export-runtime
```

The normal pack metadata is preserved, and an additional `runtime_config.json` snapshot is written so the exported pack freezes the configuration used at delivery time.

For Polygon Collision + Sprite Animation + TileSet delivery use:

```text
POST /api/v1/library/packs/export-game-ready
```

## Godot 4

Runtime-aware Godot packages add:

```text
godot4/
  assets/
  resources/
  prefabs/
    <asset_id>.tscn
  RUNTIME_IMPORT.md
```

Extract the ZIP at the Godot project root so the package remains under `res://godot4/`.

Each generated `.tscn` contains:
- `Sprite2D`
- pivot represented through Sprite2D pixel offset
- `z_index` from sorting order
- optional `StaticBody2D + CollisionShape2D` for solid box collision
- optional `Area2D + CollisionShape2D` when the box is a trigger

Game Ready export can additionally append native `CollisionPolygon2D`, generate `AnimatedSprite2D` scenes and generate TileSet EditorScripts.

The runtime exporter also corrects AtlasTexture references to the actual `res://godot4/assets/` package layout.

## Unity 2D

Runtime-aware Unity packages add:

```text
unity2d/Assets/GameCreaterPack/
  runtime_config.json
  Runtime/
    GameCreaterRuntimeMetadata.cs
  Editor/
    GameCreaterRuntimePrefabBuilder.cs
```

Copy the package's `Assets/GameCreaterPack` folder into the Unity project `Assets` folder, then run:

```text
Game Creater -> Build Runtime Asset Prefabs
```

The Editor builder:
- configures each texture as a single Sprite
- sets custom Sprite pivot
- sets Pixels Per Unit
- creates a Prefab for every asset
- sets `SpriteRenderer.sortingOrder`
- creates `BoxCollider2D` where configured
- applies `isTrigger`
- attaches `GameCreaterRuntimeMetadata` with render layer and gameplay tags

Game Ready export adds a second builder that creates PolygonCollider2D geometry, native AnimationClip `.anim` resources and Unity Tile assets.

## Advanced Library workflow

The same PR also adds operational controls required for large asset libraries:

- batch image import (up to 200 images per call)
- active-version switching / rollback without deleting newer versions
- batch non-destructive image edits
- hierarchy reparenting with cycle rejection
- asset-pack preflight validation for missing/corrupt images, Mask/Alpha size mismatches, review status and category completeness

All these operations are normal `/api/v1/*` endpoints and therefore appear automatically in the AI Native Control Layer tool catalog.
