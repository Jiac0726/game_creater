from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.asset_library_models import AssetReviewState, LibraryAssetPatch
from app.asset_workflow_maintenance_models import (
    BatchAssetEditRequest,
    PackPreflightRequest,
    ReparentAssetsRequest,
)
from app.asset_workflow_models import AssetEditOperation, AssetEditRequest
from app.services.asset_library_maintenance import AssetLibraryMaintenanceService
from app.services.asset_library_workflow import AssetLibraryWorkflowService
from app.services.pipeline import AssetSplitPipeline


def _services(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GAME_CREATER_MODE", "mock")
    workspace = tmp_path / "workspace"
    pipeline = AssetSplitPipeline(workspace)
    return (
        AssetLibraryWorkflowService(workspace, pipeline),
        AssetLibraryMaintenanceService(workspace, pipeline),
    )


def _import(workflow: AssetLibraryWorkflowService, tmp_path: Path, name: str, size=(40, 30)):
    path = tmp_path / f"{name}.png"
    Image.new("RGBA", size, (255, 255, 255, 255)).save(path)
    return workflow.import_image(path, name=name, category="prop")


def test_activate_version_rolls_asset_back_without_deleting_newer_version(tmp_path: Path, monkeypatch) -> None:
    workflow, maintenance = _services(tmp_path, monkeypatch)
    asset = _import(workflow, tmp_path, "crate", (40, 30))

    edited = workflow.edit(
        asset.id,
        AssetEditRequest(operation=AssetEditOperation.RESIZE, width=80, height=60),
    )
    assert edited.version == 2
    assert maintenance.library.get(asset.id).width == 80

    activated = maintenance.activate_version(asset.id, 1)
    assert activated.asset.active_version == 1
    assert activated.asset.width == 40
    assert activated.asset.height == 30
    assert activated.version.kind == "imported"
    assert [item.version for item in maintenance.library.list_versions(asset.id)] == [2, 1]


def test_bulk_edit_creates_independent_versions_for_each_asset(tmp_path: Path, monkeypatch) -> None:
    workflow, maintenance = _services(tmp_path, monkeypatch)
    first = _import(workflow, tmp_path, "first")
    second = _import(workflow, tmp_path, "second")

    result = maintenance.bulk_edit(
        BatchAssetEditRequest(
            asset_ids=[first.id, second.id],
            edit=AssetEditRequest(operation=AssetEditOperation.PAD, padding=4),
        )
    )

    assert result.succeeded == 2
    assert result.failed == 0
    assert {item.version for item in result.items} == {2}
    assert maintenance.library.get(first.id).width == 48
    assert maintenance.library.get(second.id).height == 38


def test_reparent_replaces_old_parent_and_rejects_cycles(tmp_path: Path, monkeypatch) -> None:
    workflow, maintenance = _services(tmp_path, monkeypatch)
    old_parent = _import(workflow, tmp_path, "old_parent")
    new_parent = _import(workflow, tmp_path, "new_parent")
    child = _import(workflow, tmp_path, "child")

    workflow.add_children(old_parent.id, [child.id])
    result = maintenance.reparent(
        new_parent.id,
        ReparentAssetsRequest(child_asset_ids=[child.id], remove_existing_parents=True),
    )

    assert result.removed_parent_links == 1
    assert workflow._direct_parents(child.id) == [new_parent.id]
    assert workflow._direct_children(old_parent.id) == []
    assert workflow._direct_children(new_parent.id) == [child.id]

    try:
        maintenance.reparent(
            child.id,
            ReparentAssetsRequest(child_asset_ids=[new_parent.id]),
        )
    except ValueError as exc:
        assert "cycle" in str(exc).lower()
    else:
        raise AssertionError("Hierarchy cycle must be rejected")


def test_pack_preflight_blocks_unreviewed_assets_and_accepts_approved_complete_asset(tmp_path: Path, monkeypatch) -> None:
    workflow, maintenance = _services(tmp_path, monkeypatch)
    asset = _import(workflow, tmp_path, "approved_asset")

    blocked = maintenance.preflight(
        PackPreflightRequest(
            asset_ids=[asset.id],
            require_reviewed=True,
            require_masks=True,
            require_alpha=True,
        )
    )
    assert blocked.valid is False
    assert any(issue.code == "review_required" for issue in blocked.issues)

    maintenance.library.patch(
        asset.id,
        LibraryAssetPatch(review_state=AssetReviewState.APPROVED),
    )
    ready = maintenance.preflight(
        PackPreflightRequest(
            asset_ids=[asset.id],
            require_reviewed=True,
            require_masks=True,
            require_alpha=True,
        )
    )
    assert ready.valid is True
    assert ready.error_count == 0
