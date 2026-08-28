# Scene Composer

Scene Composer closes the loop between Asset Library and engine scenes.

```text
Asset Library
-> Composer Scene
-> Layers
-> Asset Instances
-> Transform / Z / Y-Sort
-> Generic / Godot 4 / Unity 2D scene package
```

## Core rule

Composer items reference global Asset Library IDs. They do not duplicate source assets in persistent state. The active Asset Library version is resolved when an export is created.

Persistent composer metadata lives in:

```text
.game_creater_state/scene_composer.db
```

Export packages live under:

```text
.game_creater_state/composer_exports/
```

## Scene APIs

```text
GET  /api/v1/library/composer/scenes
POST /api/v1/library/composer/scenes
GET  /api/v1/library/composer/scenes/{scene_id}
PATCH /api/v1/library/composer/scenes/{scene_id}
```

Scene fields include canvas size, grid size and background.

## Layers

```text
POST  /api/v1/library/composer/scenes/{scene_id}/layers
PATCH /api/v1/library/composer/scenes/{scene_id}/layers/{layer_id}
```

Layers preserve order, visibility, lock state and Y-Sort intent.

## Asset instances

```text
POST   /api/v1/library/composer/scenes/{scene_id}/items
PATCH  /api/v1/library/composer/scenes/{scene_id}/items/{item_id}
DELETE /api/v1/library/composer/scenes/{scene_id}/items/{item_id}
```

Each item references one global Asset ID and stores only scene-instance state:

- X / Y
- rotation
- scale X / Y
- layer
- Z index
- visible / locked

## Human UI

The Scene Composer workspace provides:

- scene creation and switching
- layer creation and selection
- add currently selected Asset Library item
- draggable canvas placement
- numeric X/Y/rotation/scale/Z editing
- layer reassignment
- item deletion
- Godot / Unity / Generic export

## Engine delivery

### Godot 4

Generated package includes `scene.tscn`, `project.godot`, and all referenced active asset PNGs. Sprite2D nodes receive position, rotation, scale and deterministic Z ordering derived from Layer order + item Z.

### Unity 2D

Generated package includes `Assets/GameCreaterComposer`, asset PNGs, scene JSON and an Editor builder. `Game Creater -> Build Composer Scene` creates a native Unity scene using SpriteRenderer objects grouped under layer GameObjects.

## AI-native

All composer operations are typed `/api/v1/*` endpoints and therefore appear in the AI Native Control Layer. An agent can create a scene, create layers, add/move/rotate/scale assets and export the result without simulating mouse input.
