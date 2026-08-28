# Project Workspace

Project Workspace separates the global Asset Library from the exact asset versions a specific game project uses.

## Core model

```text
Game Project Workspace
├─ engine target
├─ Asset bindings
│  ├─ global Asset ID
│  ├─ role
│  └─ version policy
│     ├─ locked version
│     └─ follow active
└─ explicit asset dependencies
```

Workspace state lives in private `.game_creater_state/project_workspace.db`. No asset image is duplicated by adding it to a project.

## Locked vs follow-active

A binding created with `lock_to_current=true` freezes the current Asset Library version number. If the global asset later activates a newer version, project resolution continues using the locked version and reports `drifted=true`.

A binding in follow-active mode resolves the current global active version every time and does not report drift.

Switching between the two policies is explicit through the asset patch API.

## Dependency graph

Dependencies mean `source_asset_id` depends on `target_asset_id`. Both endpoints must already belong to the project. Cycles are rejected before mutation.

Resolution returns dependency order with prerequisites before their dependents.

## API

```text
GET    /api/v1/library/project-workspaces
POST   /api/v1/library/project-workspaces
GET    /api/v1/library/project-workspaces/{workspace_id}
PATCH  /api/v1/library/project-workspaces/{workspace_id}
POST   /api/v1/library/project-workspaces/{workspace_id}/assets
PATCH  /api/v1/library/project-workspaces/{workspace_id}/assets/{asset_id}
DELETE /api/v1/library/project-workspaces/{workspace_id}/assets/{asset_id}
POST   /api/v1/library/project-workspaces/{workspace_id}/dependencies
DELETE /api/v1/library/project-workspaces/{workspace_id}/dependencies/{source_asset_id}/{target_asset_id}
GET    /api/v1/library/project-workspaces/{workspace_id}/resolve
POST   /api/v1/library/project-workspaces/{workspace_id}/export
```

## Project lock export

Export writes:

```text
project.json
project.lock.json
```

The lock snapshot records engine target, dependency order and each resolved global Asset version/path. It is lightweight project metadata, not another duplicate Asset Pack.

## Human UI and AI

The Project Workspace panel can create projects, add currently selected Library assets, choose lock/follow behavior, inspect drift, edit dependency links and export a project lock.

Every operation is a typed `/api/v1/*` action. AI can maintain project membership and version policy directly. Removing project assets/dependencies uses DELETE actions and is confirmation-gated by the AI Native policy.
