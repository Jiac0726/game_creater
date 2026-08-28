# Advanced TileMap

This feature turns existing Asset Library TileSets into editable 2D maps while preserving AI-native control and engine-neutral data.

## Data model

```text
TileMap Project
├─ TileSet reference
├─ Width / Height
└─ Layers
   ├─ Visual
   ├─ Collision
   └─ Navigation
      └─ Cells(x,y, asset_id, terrain)
```

The map stores global Asset IDs and terrain metadata, not copied source images.

## API

```text
GET  /api/v1/library/tilemaps
POST /api/v1/library/tilemaps
GET  /api/v1/library/tilemaps/{map_id}
POST /api/v1/library/tilemaps/{map_id}/layers
POST /api/v1/library/tilemaps/{map_id}/paint
POST /api/v1/library/tilemaps/{map_id}/erase
POST /api/v1/library/tilemaps/{map_id}/export
GET  /api/v1/library/tilemaps/exports/{export_id}
```

## Terrain Painter

When painting a declared terrain on a Visual layer, the service recalculates the changed cells and their neighbors using the TileSet's `cardinal4` or `eight8` neighbor masks.

The stable bit layout remains:

- N = 1
- NE = 2
- E = 4
- SE = 8
- S = 16
- SW = 32
- W = 64
- NW = 128

For `cardinal4`, diagonal bits are ignored. Rules use exact mask matches first and fall back to the best matching rule by shared bits and priority.

## Layer intent

- `visual`: rendered Tile cells and Terrain Paint.
- `collision`: collision-design cell layer.
- `navigation`: navigation-design cell layer.

The generic map format keeps these semantics explicit so engine adapters can evolve independently.

## Godot 4 export

The export contains source textures, `tilemap_data.json`, and an EditorScript that builds:

- native `TileSet`
- `TileSetAtlasSource`
- one `TileMapLayer` per Game Creater layer
- a packed `.tscn` scene

This uses current Godot 4 `TileMapLayer` rather than the deprecated monolithic `TileMap` workflow.

## Unity 2D export

The export contains textures, `tilemap.json`, and `GameCreaterTileMapBuilder.cs`. The Editor builder creates Unity Tilemap objects and native Tile resources from the saved map definition.

## Human UI

The Advanced Tilemap panel supports:

- create/load map projects
- add Visual / Collision / Navigation layers
- select active layer
- paint asset IDs
- paint terrain names
- erase cells
- preview populated cells
- Generic / Godot / Unity export

## AI native

Every operation is a typed `/api/v1/*` action and is discoverable through `/api/v1/ai/actions` and `/api/v1/ai/tools`. AI can therefore paint terrain, erase cells, add logical layers and export without simulating mouse input.
