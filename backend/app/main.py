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

from app.models import SceneManifest
from app.services.pipeline import AssetSplitPipeline

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = REPO_ROOT / "workspace"
UPLOADS = WORKSPACE / "uploads"
EXPORTS = WORKSPACE / "exports"
FRONTEND = REPO_ROOT / "frontend"
UPLOADS.mkdir(parents=True, exist_ok=True)
EXPORTS.mkdir(parents=True, exist_ok=True)

SCENE_ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")

app = FastAPI(title="Game Creater", version="0.1.2")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

pipeline = AssetSplitPipeline(WORKSPACE)


@app.get("/api/health")
def health() -> dict:
    model = pipeline.health()
    return {
        "ok": True,
        "mode": pipeline.mode,
        "version": "0.1.2",
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


@app.get("/api/v1/scenes/{scene_id}/export.zip")
def export_scene(scene_id: str) -> FileResponse:
    if not SCENE_ID_PATTERN.fullmatch(scene_id):
        raise HTTPException(status_code=400, detail="Invalid scene id")

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


app.mount("/workspace", StaticFiles(directory=str(WORKSPACE)), name="workspace")
if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")
