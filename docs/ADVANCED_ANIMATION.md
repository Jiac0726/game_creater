# Advanced Animation

Advanced Animation builds gameplay metadata on top of the existing `anim_*` Sprite Animation clips.

```text
Animation Clip
-> State Set / Direction Map
-> Event Frames
-> Hit / Hurt / Interaction Boxes
-> Generic / Godot / Unity metadata package
```

No frame images are duplicated.

## State sets

```text
GET/POST /api/v1/library/advanced-animation/state-sets
GET/PATCH /api/v1/library/advanced-animation/state-sets/{id}
```

A state set maps gameplay state names to existing animation clip IDs, preserves a default state, optional direction-to-clip mappings and validated transitions.

## Frame events

```text
POST /api/v1/library/advanced-animation/events
GET  /api/v1/library/advanced-animation/events/{clip_id}
DELETE /api/v1/library/advanced-animation/events/{event_id}
```

Events use zero-based frame indexes and arbitrary JSON payloads. Frame indexes are validated against the current clip length.

## Frame boxes

```text
POST /api/v1/library/advanced-animation/frame-boxes
GET  /api/v1/library/advanced-animation/frame-boxes/{clip_id}
DELETE /api/v1/library/advanced-animation/frame-boxes/{box_id}
```

Hit, Hurt and Interaction rectangles use normalized 0..1 coordinates so the same metadata can be adapted to different engines and sprite sizes.

## Export

```text
POST /api/v1/library/advanced-animation/export
```

The package freezes state sets, clip definitions, events and frame boxes in `advanced_animation.json`.

Godot output includes a small GDScript state/direction adapter. Unity output includes runtime frame-box metadata and an Editor entrypoint designed to coexist with the Game Ready AnimationClip package from PR #3.

## Human UI / AI

The workspace can add event frames and boxes, create state/direction sets and export them. The same operations are typed AI Actions, so agents can configure gameplay animation semantics directly.
