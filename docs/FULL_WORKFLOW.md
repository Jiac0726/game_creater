# Game Creater v1 End-to-End Workflow

The v1 workflow connects semantic planning, image generation, automatic scene splitting,
manual correction, local completion and engine export under one persistent Project record.

## Pipeline

```text
Chinese scene concept
-> local Game Asset Ontology / SemanticEngine
-> AssetPlan
-> split-friendly generation prompt
-> ImageGenerationProvider
-> generated scene saved locally
-> AssetPlan detection prompts
-> GroundingDINO
-> bbox dedupe
-> SAM2 / SAM2.1
-> mask dedupe
-> Asset Editor
-> optional BiRefNet alpha refinement
-> optional local IOPaint / LaMa completion
-> Scene Layout
-> Godot 4 / Unity 2D export
```

## 1. Validate the whole workflow without any external API

Start Game Creater in Mock mode:

```bash
export GAME_CREATER_MODE=mock
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` and use **AI Scene Full Workflow**.
Select `mock` as the generation provider.

This validates the real workflow state machine, project persistence, semantic plan,
image handoff, split pipeline, assets and UI without a GPU or network request.

## 2. Real OpenAI image generation

Configure the API key only in the backend process:

```bash
export OPENAI_API_KEY="..."
export GAME_CREATER_OPENAI_IMAGE_MODEL="gpt-image-2"
```

Do not put the API key in the browser or frontend source.

The current provider uses the OpenAI Image API endpoint:

```text
POST /v1/images/generations
```

and stores the returned base64 image under:

```text
workspace/projects/<project_id>/generation/source.png
```

The UI provider catalog only exposes whether the server-side provider is configured.
It never returns the key.

## 3. Real automatic splitting

Use the existing Grounded-SAM2 setup:

```bash
bash scripts/setup_grounded_sam2_wsl.sh
bash scripts/start_grounded_sam2_wsl.sh
```

For a real end-to-end request the backend must run with:

```text
GAME_CREATER_MODE=grounded_sam2_local
```

The semantic `AssetPlan.detection_prompts` is passed directly into GroundingDINO after
generation. Users do not need to upload the generated image again.

## 4. Local completion with IOPaint / LaMa

The original Sanster/IOPaint repository is archived, so Game Creater treats it as a
replaceable localhost sidecar rather than a core dependency.

Install the pinned sidecar environment:

```bash
bash scripts/setup_iopaint_sidecar.sh
```

Start it:

```bash
bash scripts/start_iopaint_sidecar.sh
```

Default endpoint:

```text
http://127.0.0.1:8080
```

Game Creater checks `/api/v1/model` and calls `/api/v1/inpaint` with base64 image/mask
payloads. No arbitrary filesystem path is passed to the sidecar.

In the UI:

1. Select an extracted asset.
2. Drag a rectangle in Scene Viewer over the hidden/missing region.
3. Choose `iopaint` in **Local Completion**.
4. Run completion.

The original asset is never overwritten. Results are written to:

```text
workspace/<scene_id>/completed/
  <job_id>_scene.png
  <job_id>_<asset>.png
  <job_id>_<asset>_mask.png
  <job_id>.json
```

With real Grounded-SAM2 mode, the completed scene is automatically re-segmented for the
same asset label. In Mock mode, completion uses a deterministic fallback mask only for CI.

## 5. Project data model

```text
workspace/projects/<project_id>/
  project.json
  semantic/
    plan.json
  generation/
    request.json
    metadata.json
    source.png
```

`project.json` records workflow events and the linked `scene_id`.

Current stages:

```text
CREATED
SEMANTIC_PLANNING
PROMPT_READY
GENERATING
IMAGE_READY
DETECTING
SEGMENTING
ASSET_REVIEW
COMPLETING
ENGINE_EXPORT
DONE
FAILED
```

The first synchronous implementation persists each boundary already, so a later job
queue can resume stages without changing project files.

## 6. API

Provider catalog:

```text
GET /api/v1/generation/providers
GET /api/v1/completion/providers
```

Run semantic -> generation -> split:

```http
POST /api/v1/projects/run
Content-Type: application/json

{
  "concept": "废弃地铁站",
  "provider": "openai",
  "size": "1536x1024",
  "quality": "medium",
  "semantic_depth": 2,
  "max_per_group": 12,
  "auto_split": true
}
```

Read persisted project state:

```text
GET /api/v1/projects/<project_id>
```

Run local completion on a selected region:

```http
POST /api/v1/scenes/<scene_id>/assets/<asset_id>/complete
Content-Type: application/json

{
  "provider": "iopaint",
  "rect": {"x1": 100, "y1": 200, "x2": 360, "y2": 520},
  "prompt": "complete the hidden lower half of the wooden barrel",
  "mode": "occlusion_completion"
}
```

## 7. Current boundaries

Automatic occlusion-region detection is not yet trusted enough to silently rewrite assets.
The current completion region is explicit/user-selected, while the generated pixels are
stored separately and marked as AI-completed. This preserves provenance and prevents an
incorrect occlusion guess from corrupting the extracted source asset.

Next steps for the completion subsystem are occlusion scoring, automatic completion-region
proposal and promotion of an approved completed asset back into the main Asset list.
