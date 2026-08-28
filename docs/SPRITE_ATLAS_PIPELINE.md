# Sprite / Atlas Pipeline

This workflow optimizes many Library sprites into engine-ready texture atlases.

## OSS packing engine

Core packing uses `rectpack==0.2.2` (Apache-2.0), a mature Python rectangle-packing library supporting MaxRects/Skyline/Guillotine heuristics. Game Creater uses its default offline MaxRects-oriented packer with rotation disabled so sprite orientation never changes unexpectedly.

## API

```text
POST /api/v1/library/atlases
GET  /api/v1/library/atlases/{atlas_id}/download
```

Example:

```json
{
  "name": "forest_props",
  "asset_ids": ["asset_a", "asset_b"],
  "engine": "godot4",
  "max_width": 2048,
  "max_height": 2048,
  "padding": 2,
  "trim_transparent": true,
  "power_of_two": true
}
```

## Build behavior

1. Resolve the current active Asset Library image version.
2. Optionally trim transparent borders without mutating the source asset.
3. Add requested padding around each packed rectangle.
4. Pack rectangles using `rectpack`.
5. Spill into additional atlas pages when necessary.
6. Optionally round each used page size to power-of-two dimensions.
7. Write `atlas.json` with source size, trim offsets, page and packed rectangle.
8. Generate Generic, Godot 4 or Unity 2D delivery files.

Persistent source assets remain unchanged. Atlas packages are generated under private `.game_creater_state/atlas_exports`.

## Godot 4

Each packed sprite receives a native `AtlasTexture` `.tres` resource pointing at the appropriate page and `Rect2` region.

## Unity 2D

The generated Editor importer configures each atlas page as `SpriteImportMode.Multiple` and writes `SpriteMetaData` rectangles. The Y coordinate is converted from Game Creater's top-left atlas coordinates to Unity's Sprite rect convention.

## Human UI

The Sprite / Atlas panel builds an atlas from checked Asset Library items and exposes max texture size, padding, Trim, power-of-two and target-engine options.

## AI-native

Atlas build is one typed action. Agents can select an asset set, choose constraints and create the same engine package without UI automation.
