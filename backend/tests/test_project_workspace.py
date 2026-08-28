from __future__ import annotations

import json
import zipfile
from pathlib import Path

from PIL import Image
import pytest

from app.project_workspace_models import (
    ProjectWorkspaceCreate,
    WorkspaceAssetAddRequest,
    WorkspaceAssetPatch,
    WorkspaceDependencyCreate,
)
from app.services.asset_library_workflow import AssetLibraryWorkflowService
from app.services.pipeline import AssetSplitPipeline
from app.services.project_workspace import ProjectWorkspaceService


def _setup(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GAME_CREATER_MODE", "mock")
    workspace = tmp_path / "workspace"
    workflow = AssetLibraryWorkflowService(workspace, AssetSplitPipeline(workspace))
    projects = ProjectWorkspaceService(workspace)
    return workspace, workflow, projects


def _asset(workflow: AssetLibraryWorkflowService, tmp_path: Path, name: str):
    path = tmp_path / f"{name}.png"
    Image.new("RGBA", (32, 32), (255, 255, 255, 255)).save(path)
    return workflow.import_image(path, name=name, category="prop")


def test_locked_asset_reports_drift_until_follow_active(tmp_path: Path, monkeypatch) -> None:
    workspace, workflow, projects = _setup(tmp_path, monkeypatch)
    asset = _asset(workflow, tmp_path, "tree")
    project = projects.create(ProjectWorkspaceCreate(name="My Game", engine="godot4"))
    project = projects.add_assets(project.id, WorkspaceAssetAddRequest(asset_ids=[asset.id], lock_to_current=True, role="environment"))
    assert project.assets[0].locked_version == 1
    assert project.assets[0].follows_active is False

    v2_rel = f"library_versions/{asset.id}/project_v2.png"
    v2_path = workspace / v2_rel
    v2_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (32, 32), (0, 255, 0, 255)).save(v2_path)
    projects.library.add_version(asset.id, kind="project_test", image_path=v2_rel, activate=True)

    resolution = projects.resolve(project.id)
    assert resolution.drift_count == 1
    assert resolution.assets[0].locked_version == 1
    assert resolution.assets[0].active_version == 2
    assert resolution.assets[0].resolved_version == 1
    assert resolution.assets[0].drifted is True

    projects.patch_asset(project.id, asset.id, WorkspaceAssetPatch(follow_active=True))
    resolution = projects.resolve(project.id)
    assert resolution.drift_count == 0
    assert resolution.assets[0].resolved_version == 2
    assert resolution.assets[0].follows_active is True


def test_dependency_order_and_cycle_rejection(tmp_path: Path, monkeypatch) -> None:
    _, workflow, projects = _setup(tmp_path, monkeypatch)
    a = _asset(workflow, tmp_path, "character")
    b = _asset(workflow, tmp_path, "accessory")
    c = _asset(workflow, tmp_path, "effect")
    project = projects.create(ProjectWorkspaceCreate(name="Dependencies"))
    projects.add_assets(project.id, WorkspaceAssetAddRequest(asset_ids=[a.id, b.id, c.id]))
    projects.add_dependency(project.id, WorkspaceDependencyCreate(source_asset_id=a.id, target_asset_id=b.id, reason="character uses accessory"))
    projects.add_dependency(project.id, WorkspaceDependencyCreate(source_asset_id=b.id, target_asset_id=c.id, reason="accessory uses effect"))
    resolution = projects.resolve(project.id)
    assert resolution.dependency_order.index(c.id) < resolution.dependency_order.index(b.id) < resolution.dependency_order.index(a.id)

    with pytest.raises(ValueError, match="cycle"):
        projects.add_dependency(project.id, WorkspaceDependencyCreate(source_asset_id=c.id, target_asset_id=a.id))
    persisted = projects.get(project.id)
    assert not any(d.source_asset_id == c.id and d.target_asset_id == a.id for d in persisted.dependencies)


def test_remove_asset_cleans_project_dependencies_and_export_freezes_resolution(tmp_path: Path, monkeypatch) -> None:
    _, workflow, projects = _setup(tmp_path, monkeypatch)
    a = _asset(workflow, tmp_path, "a")
    b = _asset(workflow, tmp_path, "b")
    project = projects.create(ProjectWorkspaceCreate(name="Export", engine="unity2d"))
    projects.add_assets(project.id, WorkspaceAssetAddRequest(asset_ids=[a.id, b.id], lock_to_current=True))
    projects.add_dependency(project.id, WorkspaceDependencyCreate(source_asset_id=a.id, target_asset_id=b.id))

    exported = projects.export(project.id)
    with zipfile.ZipFile(exported.archive_path) as archive:
        lock = json.loads(archive.read("project.lock.json"))
        assert lock["workspace_id"] == project.id
        assert {item["asset_id"] for item in lock["assets"]} == {a.id, b.id}
        assert all(item["resolved_version"] == 1 for item in lock["assets"])

    project = projects.remove_asset(project.id, b.id)
    assert [item.asset_id for item in project.assets] == [a.id]
    assert project.dependencies == []
