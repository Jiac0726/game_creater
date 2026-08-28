# Engine Sync

Engine Sync removes the repeated ZIP-import step for local Godot 4 and Unity 2D projects.

## Safety boundary

A profile points at a local engine project root, but Game Creater may write only inside a dedicated managed namespace:

```text
Godot 4: <project>/GameCreaterAssets/
Unity 2D: <project>/Assets/GameCreater/
```

Godot roots must contain `project.godot`. Unity roots must contain both `Assets/` and `ProjectSettings/`.

This is a local-first feature. Do not expose a server with filesystem project access to untrusted public users.

## Incremental plan

Each selected global Asset ID resolves its current active Library version plus runtime configuration. Desired files include:

```text
assets/<asset_id>.png
masks/<asset_id>.png
alpha/<asset_id>.png
metadata/<asset_id>.json
game_creater_manifest.json
```

SHA-256 is calculated for desired sources and current target files. A plan labels every managed file as:

- `add`
- `update`
- `unchanged`
- `stale`

A normal sync only copies `add` and `update`. It never deletes stale output.

## Explicit stale cleanup

Stale cleanup is a separate DELETE action. The service recalculates the current plan and only accepts paths that are still reported as stale. Resolved targets are checked to remain inside the managed root.

This gives the AI Native policy a destructive surface it can confirmation-gate independently from ordinary sync.

## API

```text
GET    /api/v1/library/engine-sync/profiles
POST   /api/v1/library/engine-sync/profiles
GET    /api/v1/library/engine-sync/profiles/{profile_id}
PATCH  /api/v1/library/engine-sync/profiles/{profile_id}
GET    /api/v1/library/engine-sync/profiles/{profile_id}/plan
POST   /api/v1/library/engine-sync/profiles/{profile_id}/sync
DELETE /api/v1/library/engine-sync/profiles/{profile_id}/stale
```

## Human UI

The Engine Sync panel can:

- create a Godot or Unity local project profile
- use currently selected Asset Library assets
- preview add/update/unchanged/stale operations
- apply an incremental sync
- explicitly prune only reported stale managed files

## AI native

Every operation is a typed `/api/v1/*` action. AI can create profiles, calculate dry-run plans and sync directly. Stale deletion is a separate DELETE operation and therefore requires confirmation under the AI control policy.
