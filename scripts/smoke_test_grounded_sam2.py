#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def load_env_file(path: Path) -> None:
    if not path.is_file():
        raise SystemExit(f"Environment file not found: {path}")
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = os.path.expandvars(os.path.expanduser(value.strip().strip('"').strip("'")))


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Run one real GroundingDINO + SAM2 Game Creater pipeline smoke test")
    parser.add_argument("--image", required=True, help="PNG/JPG/WEBP game-scene image")
    parser.add_argument("--prompts", default="", help="Comma-separated English detection prompts")
    parser.add_argument("--keyword", default="", help="Chinese/English scene concept expanded by the local ontology")
    parser.add_argument(
        "--env-file",
        default=os.getenv("GAME_CREATER_ENV_FILE", str(Path.home() / ".config/game_creater/grounded_sam2.env")),
    )
    parser.add_argument("--workspace", default=str(repo_root / "validation_output"))
    args = parser.parse_args()

    image_path = Path(args.image).expanduser().resolve()
    if not image_path.is_file():
        raise SystemExit(f"Image not found: {image_path}")
    if image_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise SystemExit("Image must be PNG, JPG, JPEG or WEBP")

    load_env_file(Path(args.env_file).expanduser())
    os.environ["GAME_CREATER_MODE"] = "grounded_sam2_local"

    sys.path.insert(0, str(repo_root / "backend"))
    from app.services.pipeline import AssetSplitPipeline
    from app.services.semantic_engine import SemanticEngine

    prompts = [item.strip() for item in args.prompts.split(",") if item.strip()]
    if args.keyword.strip():
        expansion = SemanticEngine().expand(args.keyword.strip(), depth=1, max_per_group=30)
        if not expansion.detection_prompts:
            raise SystemExit(f"Keyword did not produce detection prompts: {args.keyword}")
        prompts = expansion.detection_prompts
    if not prompts:
        raise SystemExit("Provide --prompts or --keyword")

    workspace = Path(args.workspace).expanduser().resolve()
    pipeline = AssetSplitPipeline(workspace)
    health = pipeline.health()
    if not health.get("ready"):
        print(json.dumps({"health": health}, ensure_ascii=False, indent=2))
        raise SystemExit("Grounded-SAM2 backend is not ready")

    manifest = pipeline.run(image_path, prompts)
    scene_dir = workspace / manifest.scene_id

    missing_files: list[str] = []
    for relative in [manifest.preview_image, manifest.source_file, "scene.json"]:
        if relative and not (scene_dir / relative).is_file():
            missing_files.append(relative)
    for asset in manifest.assets:
        for relative in (asset.image, asset.mask):
            if not (scene_dir / relative).is_file():
                missing_files.append(relative)

    summary = {
        "ok": not missing_files,
        "scene_id": manifest.scene_id,
        "scene_dir": str(scene_dir),
        "image": str(image_path),
        "prompt_count": len(prompts),
        "asset_count": len(manifest.assets),
        "inference_stats": manifest.inference_stats,
        "missing_files": missing_files,
        "assets": [
            {
                "id": asset.id,
                "label": asset.label,
                "confidence": asset.confidence,
                "asset_score": asset.asset_score,
                "bbox": asset.bbox.model_dump(),
            }
            for asset in manifest.assets
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
