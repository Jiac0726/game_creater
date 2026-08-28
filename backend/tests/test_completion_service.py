from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.completion_models import AssetCompletionRequest
from app.models import BBox
from app.services.completion_service import CompletionService
from app.services.pipeline import AssetSplitPipeline


def test_mock_completion_keeps_original_asset_and_writes_completed_outputs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GAME_CREATER_MODE", "mock")
    source = tmp_path / "source.png"
    Image.new("RGB", (180, 120), "white").save(source)
    workspace = tmp_path / "workspace"
    pipeline = AssetSplitPipeline(workspace)
    manifest = pipeline.run(source, ["tree", "crate"])
    asset = manifest.assets[0]
    original_asset_path = workspace / manifest.scene_id / asset.image
    before = original_asset_path.read_bytes()

    rect = BBox(
        x1=max(0, asset.bbox.x1),
        y1=max(0, asset.bbox.y1),
        x2=min(manifest.width, asset.bbox.x2),
        y2=min(manifest.height, asset.bbox.y1 + max(2, (asset.bbox.y2 - asset.bbox.y1) // 4)),
    )
    result = CompletionService(workspace, pipeline).complete(
        manifest.scene_id,
        asset.id,
        AssetCompletionRequest(rect=rect, provider="mock"),
    )

    scene_dir = workspace / manifest.scene_id
    assert result.provider == "mock"
    assert result.resegmented is False
    assert (scene_dir / result.completed_scene).is_file()
    assert (scene_dir / result.completed_asset).is_file()
    assert (scene_dir / result.completed_mask).is_file()
    assert (scene_dir / "completed" / f"{result.job_id}.json").is_file()
    assert original_asset_path.read_bytes() == before
    assert result.metadata["original_asset_unchanged"] is True
