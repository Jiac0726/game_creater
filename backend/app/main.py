from __future__ import annotations

import os
import re
import shutil
import zipfile
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.models import (
    AssetEdgeRefineRequest,
    AssetMergeRequest,
    AssetPatch,
    AssetPointSegmentRequest,
    AssetRecord,
    AssetSplitRequest,
    SceneManifest,
    SceneRecommendRequest,
    SceneRecommendations,
    SemanticExpandRequest,
    SemanticExpansion,
)
from app.services.asset_editor import AssetEditor
from app.services.birefnet_sidecar import BiRefNetSidecarError
from app.services.edge_refinement import EdgeRefinementService
from app.services.godot_exporter import GodotExporter
from app.services.library_index import LibraryIndex
from app.services.pipeline import AssetSplitPipeline
from app.services.scene_recommender import SceneRecommender
from app.services.scene_store import AssetNotFoundError, SceneNotFoundError, SceneStore
from app.services.semantic_engine import SemanticEngine
from app.services.unity_exporter import UnityExporter
from app.store_api import build_store_router
from app.workflow_api import build_workflow_router

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = REPO_ROOT / "workspace"
UPLOADS = WORKSPACE / "uploads"
EXPORTS = WORKSPACE / "exports"
FRONTEND = REPO_ROOT / "frontend"
UPLOADS.mkdir(parents=True, exist_ok=True)
EXPORTS.mkdir(parents=True, exist_ok=True)

SCENE_ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")
EDGE_REFINER_MODE = os.getenv("GAME_CREATER_EDGE_REFINER", "none").strip().lower()

app = FastAPI(title="Game Creater", version="1.1.0-dev")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

pipeline = AssetSplitPipeline(WORKSPACE)
scene_store = SceneStore(WORKSPACE)
asset_editor = AssetEditor(WORKSPACE)
semantic_engine = SemanticEngine()
scene_recommender = SceneRecommender()
edge_refiner = EdgeRefinementService(WORKSPACE)
godot_exporter = GodotExporter(WORKSPACE, EXPORTS)
unity_exporter = UnityExporter(WORKSPACE, EXPORTS)
library_index = LibraryIndex(WORKSPACE)
app.include_router(build_workflow_router(WORKSPACE, pipeline))
app.include_router(build_store_router(WORKSPACE), prefix="/api/v1")


def _edge_status() -> dict:
    if EDGE_REFINER_MODE != "birefnet_sidecar":
        return {"enabled": False, "mode": EDGE_REFINER_MODE, "ready": False}
    status = edge_refiner.health()
    return {"enabled": True, "mode": EDGE_REFINER_MODE, **status}


@app.get("/api/health")
def health() -> dict:
    model = pipeline.health()
    return {
        "ok": True,
        "mode": pipeline.mode,
        "version": "1.1.0-dev",
        "model": model,
        "semantic": {
            "ready": True,
            "offline": True,
            "concept_count": len(semantic_engine.concepts),
            "modifier_count": len(semantic_engine.modifiers),
        },
        "edge_refiner": {
            "enabled": EDGE_REFINER_MODE == "birefnet_sidecar",
            "mode": EDGE_REFINER_MODE,
        },
        "generation_workflow": True,
        "asset_store": True,
        "engine_export": {"godot4": True, "unity2d": True},
    }


@app.get("/api/v1/models/status")
def model_status() -> dict:
    return pipeline.health()


@app.get("/api/v1/library")
def get_library_index() -> dict:
    return library_index.build()


@app.get("/api/v1/scenes/{scene_id}", response_model=SceneManifest)
def get_scene(scene_id: str) -> SceneManifest:
    _validate_scene_id(scene_id)
    try:
        manifest = scene_store.load(scene_id)
        if not library_index.manifest_paths_are_safe(manifest):
            raise HTTPException(status_code=400, detail="Scene contains an invalid project-relative path")
        return manifest
    except SceneNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Scene not found") from exc


@app.get("/api/v1/edge-refiner/status")
def edge_refiner_status() -> dict:
    return _edge_status()


@app.get("/api/v1/semantic/catalog")
def semantic_catalog() -> dict:
    return semantic_engine.catalog()


@app.post("/api/v1/semantic/expand", response_model=SemanticExpansion)
def semantic_expand(request: SemanticExpandRequest) -> SemanticExpansion:
    try:
        return semantic_engine.expand(
            request.keyword,
            depth=request.depth,
            max_per_group=request.max_per_group,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


@app.post(
    "/api/v1/scenes/{scene_id}/recommendations",
    response_model=SceneRecommendations,
)
def recommend_missing_assets(
    scene_id: str,
    request: SceneRecommendRequest,
) -> SceneRecommendations:
    _validate_scene_id(scene_id)
    try:
        manifest = scene_store.load(scene_id)
        expansion = semantic_engine.expand(request.keyword, depth=1, max_per_group=30)
        return scene_recommender.recommend(
            manifest,
            expansion,
            max_results=request.max_results,
            min_semantic_score=request.min_semantic_score,
        )
    except SceneNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Scene not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post(
    "/api/v1/scenes/{scene_id}/assets/point-segment",
    response_model=SceneManifest,
)
def point_segment_asset(
    scene_id: str,
    request: AssetPointSegmentRequest,
) -> SceneManifest:
    _validate_scene_id(scene_id)
    if pipeline.mode not in {"grounded_sam2", "grounded_sam2_local"}:
        raise HTTPException(
            status_code=503,
            detail="Interactive SAM point segmentation requires grounded_sam2_local mode",
        )

    try:
        manifest = scene_store.load(scene_id)
        if not manifest.source_file:
            raise ValueError("Scene has no retained source image")
        source_path = WORKSPACE / scene_id / manifest.source_file
        if not source_path.is_file():
            raise ValueError("Retained source image is missing")
        if not request.points:
            raise ValueError("At least one SAM point prompt is required")

        existing = None
        box = None
        if request.asset_id:
            existing = next(
                (asset for asset in manifest.assets if asset.id == request.asset_id),
                None,
            )
            if existing is None:
                raise AssetNotFoundError(request.asset_id)
            if request.use_asset_box:
                box = (
                    existing.bbox.x1,
                    existing.bbox.y1,
                    existing.bbox.x2,
                    existing.bbox.y2,
                )

        label = (request.label or (existing.label if existing else "asset")).strip()
        points = [(point.x, point.y) for point in request.points]
        point_labels = [1 if point.positive else 0 for point in request.points]
        mask, sam_score = pipeline._get_grounded_adapter().segment_points(
            source_path,
            points,
            point_labels,
            box=box,
        )
        confidence = min(1.0, max(0.0, float(sam_score)))

        return asset_editor.upsert_from_mask(
            scene_id,
            mask,
            label=label,
            category=request.category,
            notes=request.notes,
            confidence=confidence,
            replace_asset_id=request.asset_id,
        )
    except SceneNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Scene not found") from exc
    except AssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Asset not found") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post(
    "/api/v1/scenes/{scene_id}/assets/{asset_id}/refine-edge",
    response_model=AssetRecord,
)
def refine_asset_edge(
    scene_id: str,
    asset_id: str,
    request: AssetEdgeRefineRequest,
) -> AssetRecord:
    _validate_scene_id(scene_id)
    if EDGE_REFINER_MODE != "birefnet_sidecar":
        raise HTTPException(
            status_code=503,
            detail="BiRefNet edge refinement is disabled. Set GAME_CREATER_EDGE_REFINER=birefnet_sidecar.",
        )
    try:
        return edge_refiner.refine(scene_id, asset_id, radius=request.radius)
    except SceneNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Scene not found") from exc
    except AssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Asset not found") from exc
    except BiRefNetSidecarError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


@app.delete(
    "/api/v1/scenes/{scene_id}/assets/{asset_id}",
    response_model=SceneManifest,
)
def delete_asset(scene_id: str, asset_id: str) -> SceneManifest:
    _validate_scene_id(scene_id)
    try:
        return asset_editor.delete(scene_id, asset_id)
    except SceneNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Scene not found") from exc
    except AssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Asset not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post(
    "/api/v1/scenes/{scene_id}/assets/merge",
    response_model=SceneManifest,
)
def merge_assets(scene_id: str, request: AssetMergeRequest) -> SceneManifest:
    _validate_scene_id(scene_id)
    try:
        return asset_editor.merge(scene_id, request)
    except SceneNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Scene not found") from exc
    except AssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Asset not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post(
    "/api/v1/scenes/{scene_id}/assets/{asset_id}/split",
    response_model=SceneManifest,
)
def split_asset(
    scene_id: str,
    asset_id: str,
    request: AssetSplitRequest,
) -> SceneManifest:
    _validate_scene_id(scene_id)
    try:
        return asset_editor.split(scene_id, asset_id, request)
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


@app.get("/api/v1/scenes/{scene_id}/export/godot.zip")
def export_scene_godot(scene_id: str) -> FileResponse:
    _validate_scene_id(scene_id)
    try:
        archive_path = godot_exporter.export(scene_id)
    except SceneNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Scene not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(
        path=archive_path,
        media_type="application/zip",
        filename=f"game_creater_{scene_id}_godot4.zip",
    )


@app.get("/api/v1/scenes/{scene_id}/export/unity.zip")
def export_scene_unity(scene_id: str) -> FileResponse:
    _validate_scene_id(scene_id)
    try:
        archive_path = unity_exporter.export(scene_id)
    except SceneNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Scene not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(
        path=archive_path,
        media_type="application/zip",
        filename=f"game_creater_{scene_id}_unity2d.zip",
    )


def _validate_scene_id(scene_id: str) -> None:
    if not SCENE_ID_PATTERN.fullmatch(scene_id):
        raise HTTPException(status_code=400, detail="Invalid scene id")


app.mount("/workspace", StaticFiles(directory=str(WORKSPACE)), name="workspace")
if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")
