from __future__ import annotations

from pathlib import Path

from PIL import Image
import pytest

from app.engine_sync_models import EngineSyncEngine, EngineSyncProfileCreate
from app.services.asset_library_workflow import AssetLibraryWorkflowService
from app.services.engine_sync import EngineSyncService
from app.services.pipeline import AssetSplitPipeline


def _setup(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GAME_CREATER_MODE", "mock")
    workspace = tmp_path / "workspace"
    workflow = AssetLibraryWorkflowService(workspace, AssetSplitPipeline(workspace))
    sync = EngineSyncService(workspace)
    return workspace, workflow, sync


def _asset(workflow: AssetLibraryWorkflowService, tmp_path: Path, name: str):
    path = tmp_path / f"{name}.png"
    Image.new("RGBA", (32, 32), (255, 255, 255, 255)).save(path)
    return workflow.import_image(path, name=name, category="prop")


def _godot_project(tmp_path: Path) -> Path:
    root = tmp_path / "godot_project"
    root.mkdir()
    (root / "project.godot").write_text('[application]\nconfig/name="Test"\n', encoding="utf-8")
    return root


def _unity_project(tmp_path: Path) -> Path:
    root = tmp_path / "unity_project"
    (root / "Assets").mkdir(parents=True)
    (root / "ProjectSettings").mkdir()
    return root


def test_godot_sync_is_incremental_and_prune_is_explicit(tmp_path: Path, monkeypatch) -> None:
    workspace, workflow, sync = _setup(tmp_path, monkeypatch)
    asset = _asset(workflow, tmp_path, "tree")
    project = _godot_project(tmp_path)
    profile = sync.create(
        EngineSyncProfileCreate(
            name="Godot local",
            engine=EngineSyncEngine.GODOT4,
            project_root=str(project),
            asset_ids=[asset.id],
        )
    )
    assert profile.managed_root == "GameCreaterAssets"

    first_plan = sync.plan(profile.id)
    assert first_plan.add_count >= 3
    assert first_plan.update_count == 0
    first = sync.sync(profile.id)
    assert first.copied
    assert (project / "GameCreaterAssets" / "assets" / f"{asset.id}.png").is_file()

    second_plan = sync.plan(profile.id)
    assert second_plan.add_count == 0
    assert second_plan.update_count == 0
    second = sync.sync(profile.id)
    assert second.copied == []
    assert second.unchanged

    new_rel = f"library_versions/{asset.id}/sync_v2.png"
    new_path = workspace / new_rel
    new_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (32, 32), (0, 255, 0, 255)).save(new_path)
    sync.library.add_version(asset.id, kind="sync_test", image_path=new_rel, activate=True)
    changed = sync.plan(profile.id)
    assert any(item.relative_path == f"assets/{asset.id}.png" and item.action == "update" for item in changed.files)
    sync.sync(profile.id)

    stale = project / "GameCreaterAssets" / "old.tmp"
    stale.write_text("old", encoding="utf-8")
    stale_plan = sync.plan(profile.id)
    assert "old.tmp" in stale_plan.stale_paths
    assert stale.is_file()
    pruned = sync.prune(profile.id, ["old.tmp"])
    assert pruned.removed == ["old.tmp"]
    assert not stale.exists()

    with pytest.raises(ValueError, match="only paths currently reported as stale"):
        sync.prune(profile.id, [f"assets/{asset.id}.png"])


def test_unity_sync_is_restricted_to_assets_gamecreater(tmp_path: Path, monkeypatch) -> None:
    _, workflow, sync = _setup(tmp_path, monkeypatch)
    asset = _asset(workflow, tmp_path, "barrel")
    project = _unity_project(tmp_path)
    profile = sync.create(
        EngineSyncProfileCreate(
            name="Unity local",
            engine=EngineSyncEngine.UNITY2D,
            project_root=str(project),
            asset_ids=[asset.id],
        )
    )
    assert profile.managed_root == "Assets/GameCreater"
    result = sync.sync(profile.id)
    assert result.copied
    assert (project / "Assets" / "GameCreater" / "assets" / f"{asset.id}.png").is_file()
    assert not (project / "Assets" / f"{asset.id}.png").exists()


def test_profile_requires_real_engine_project_marker(tmp_path: Path, monkeypatch) -> None:
    _, workflow, sync = _setup(tmp_path, monkeypatch)
    asset = _asset(workflow, tmp_path, "invalid")
    root = tmp_path / "not_engine"
    root.mkdir()
    with pytest.raises(ValueError, match="project.godot"):
        sync.create(EngineSyncProfileCreate(name="Bad", engine="godot4", project_root=str(root), asset_ids=[asset.id]))
