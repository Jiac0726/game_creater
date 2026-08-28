# AI-Native Control Contract

Game Creater treats AI control as a product-level requirement rather than an optional chatbot feature.

## Core rule

Every user-visible business operation must exist as a backend API capability first.
The browser UI, scripts, automation and AI agents must call the same capability.

```text
User UI ───────┐
               ├─> FastAPI product operation ─> service/domain layer
AI Agent ──────┘
```

A business mutation that exists only inside frontend JavaScript is considered an architecture violation.

## Action discovery

Game Creater derives the AI action catalog directly from the FastAPI OpenAPI contract.
There is no second hand-written action implementation that can drift away from the real product API.

```text
GET /api/v1/ai/actions
GET /api/v1/ai/actions/<action_id>
GET /api/v1/ai/tools
GET /api/v1/ai/policy
```

Every non-AI `/api/v1/*` operation becomes one stable action id based on its HTTP method and path.

Examples:

```text
POST   /api/v1/projects/run
-> post.projects.run

PATCH  /api/v1/library/assets/{asset_id}
-> patch.library.assets.asset_id

POST   /api/v1/store/checkout
-> post.store.checkout

DELETE /api/v1/scenes/{scene_id}/assets/{asset_id}
-> delete.scenes.scene_id.assets.asset_id
```

The `/api/v1/ai/*` endpoints themselves are excluded to prevent recursive tool generation.

## Tool schema

`GET /api/v1/ai/tools` returns function-tool definitions suitable for an LLM/agent adapter.
Pydantic/OpenAPI `$ref` request models are expanded into self-contained JSON Schema so agents can see complete nested parameters without loading OpenAPI components separately.

Each tool contains:

```text
function.name
function.description
function.parameters
x-game-creater-action
x-http-method
x-http-path
x-risk
x-requires-confirmation
```

The AI layer is discovery and policy metadata. It does not proxy or reimplement the action.
The agent invokes the declared real product API endpoint.

## Risk policy

All operations are AI-operable, but AI-operable does not mean silently executable.

Current default classification:

| Risk | Examples | Confirmation |
|---|---|---|
| read | search, status, catalog, versions | no |
| write | rename, tags, collections, ordinary edits | no by default |
| expensive | image generation, SAM point segmentation, completion, edge refine | yes |
| destructive | delete asset, remove membership | yes |
| commerce | checkout, seller listing publication changes | yes |

An embedded agent should ask for explicit user approval immediately before executing an action marked `x-requires-confirmation=true`.

## Coverage requirement

CI verifies that every current non-AI `/api/v1/*` product operation appears exactly once in the AI action catalog.
This means a future feature PR that adds a backend API automatically becomes discoverable by AI.

For future product work, use this checklist:

1. Put business logic in a service/domain layer.
2. Expose it through a typed `/api/v1/*` API.
3. Make UI call that API rather than duplicate the business logic.
4. Verify the operation appears in `/api/v1/ai/actions` and `/api/v1/ai/tools`.
5. Assign confirmation/risk policy if the operation spends money, incurs model cost, deletes data or has other irreversible effects.
6. Add a regression test for the feature-specific action when appropriate.

## Direction

This control layer is intentionally model-agnostic. A future embedded agent can use local models, OpenAI, Claude or an MCP adapter without changing Asset Library, Store, Editor, Scene or Workflow domain code.

The intended long-term architecture is:

```text
Natural language
-> Planner
-> AI Tool Catalog
-> Action selection
-> Confirmation policy
-> real Game Creater API
-> audit/result
-> next action
```

The planner/model may change. The action contract remains the stable product surface.
