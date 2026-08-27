from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from app.models import AssetPatch
from app.services.pipeline import AssetSplitPipeline
from app.services.scene_store import AssetNotFoundError, SceneStore


def _scene(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GAME_CREATER_MODE", "mock")
    source = tmp_path / "scene.png"
    Image.new("RGB", (64, 48), "white").save(source)
    workspace = tmp_path / "workspace"
    manifest = AssetSplitPipeline(workspace).run(source, ["tree", "rock"])
    return workspace, manifest


def test_patch_asset_persists_label_category_and_notes(tmp_path: Path, monkeypatch) -> None:
    workspace, manifest = _scene(tmp_path, monkeypatch)
    store = SceneStore(workspace)

    updated = store.patch_asset(
        manifest.scene_id,
        manifest.assets[0].id,
        AssetPatch(label="Ancient Tree", category="vegetation", notes="hero prop"),
    )

    assert updated.label == "Ancient Tree"
    assert updated.category == "vegetation"
    assert updated.notes == "hero prop"

    reloaded = store.load(manifest.scene_id)
    persisted = reloaded.assets[0]
    assert persisted.label == "Ancient Tree"
    assert persisted.category == "vegetation"
    assert persisted.notes == "hero prop"


def test_patch_asset_rejects_empty_label(tmp_path: Path, monkeypatch) -> None:
    workspace, manifest = _scene(tmp_path, monkeypatch)
    store = SceneStore(workspace)

    with pytest.raises(ValueError, match="cannot be empty"):
        store.patch_asset(
            manifest.scene_id,
            manifest.assets[0].id,
            AssetPatch(label="   "),
        )


def test_patch_missing_asset_raises(tmp_path: Path, monkeypatch) -> None:
    workspace, manifest = _scene(tmp_path, monkeypatch)
    store = SceneStore(workspace)

    with pytest.raises(AssetNotFoundError):
        store.patch_asset(manifest.scene_id, "asset_9999", AssetPatch(label="missing"))
