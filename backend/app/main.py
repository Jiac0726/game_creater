from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.models import AssetPatch, AssetRecord, SceneManifest
from app.services.pipeline import AssetSplitPipeline
from app.services.scene_store import AssetNotFoundError, SceneNotFoundError, SceneStore

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = REPO_ROOT / "workspace"
UPLOADS = WORKSPACE / "uploads"
EXPORTS = WORKSPACE / "exports"
FRONTEND = REPO_ROOT / "frontend"
UPLOADS.mkdir(parents=True, exist_ok=True)
EXPORTS.mkdir(parents=True, exist_ok=True)

SCENE_ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")

app = FastAPI(title="Game Creater", version="0.2.0-dev")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

pipeline = AssetSplitPipeline(WORKSPACE)
scene_store = SceneStore(WORKSPACE)


@app.get("/api/health")
def health() -> dict:
    model = pipeline.health()
    return {
        "ok": True,
        "mode": pipeline.mode,
        "version": "0.2.0-dev",
        "model": model,
    }


@app.get("/api/v1/models/status")
def model_status() -> dict:
    return pipeline.health()


@app.post("/api/v1/scenes/analyze", response_model=SceneManifest)
def analyze_scene(
    image: UploadFile = File(...),
    prompts: str = Form("asset"),
) -> SceneManifest:
    suffix = Path(image.filename or "scene.png").suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(status_code=400, detail="Supported formats: PNG, JPG, JPEG, WEBP")

    upload_path = UPLOADS / f"{uuid4().hex}{suffix}"
    with upload_path.open("wb") as output:
        shutil.copyfileobj(image.file, output)

    labels = [
        item.strip()
        for item in prompts.replace("\n", ",").replace("。", ",").replace(".", ",").split(",")
        if item.strip()
    ]

    try:
        return pipeline.run(upload_path, labels)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.patch(
    "/api/v1/scenes/{scene_id}/assets/{asset_id}",
    response_model=AssetRecord,
)
def patch_asset(scene_id: str, asset_id: str, patch: AssetPatch) -> AssetRecord:
    _validate_scene_id(scene_id)
    try:
        return scene_store.patch_asset(scene_id, asset_id, patch)
    except SceneNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Scene not found") from exc
    except AssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Asset not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/scenes/{scene_id}/export.zip")
def export_scene(scene_id: str) -> FileResponse:
    _validate_scene_id(scene_id)

    scene_dir = WORKSPACE / scene_id
    if not scene_dir.is_dir() or not (scene_dir / "scene.json").is_file():
        raise HTTPException(status_code=404, detail="Scene not found")

    archive_path = EXPORTS / f"{scene_id}.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(scene_dir.rglob("*")):
            if path.is_file():
                archive.write(path, arcname=path.relative_to(scene_dir))

    return FileResponse(
        path=archive_path,
        media_type="application/zip",
        filename=f"game_creater_{scene_id}.zip",
    )


def _validate_scene_id(scene_id: str) -> None:
    if not SCENE_ID_PATTERN.fullmatch(scene_id):
        raise HTTPException(status_code=400, detail="Invalid scene id")


app.mount("/workspace", StaticFiles(directory=str(WORKSPACE)), name="workspace")
if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")
