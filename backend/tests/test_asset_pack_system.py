from __future__ import annotations

import json
import zipfile
from pathlib import Path

from PIL import Image
import pytest

from app.asset_pack_models import (
    AssetPackCreateRequest,
    AssetPackDependency,
    AssetPackReleaseRequest,
    AssetPackUpdateRequest,
)
from app.services.asset_library_workflow import AssetLibraryWorkflowService
from app.services.asset_pack_system import AssetPackSystemService
from app.services.pipeline import AssetSplitPipeline


def _setup(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GAME_CREATER_MODE", "mock")
    workspace = tmp_path / "workspace"
    workflow = AssetLibraryWorkflowService(workspace, AssetSplitPipeline(workspace))
    packs = AssetPackSystemService(workspace)
    return workspace, workflow, packs


def _asset(workflow: AssetLibraryWorkflowService, tmp_path: Path, name: str):
    path = tmp_path / f"{name}.png"
    Image.new("RGBA", (32, 32), (255, 255, 255, 255)).save(path)
    return workflow.import_image(path, name=name, category="prop")


def test_release_pins_dependency_and_install_builds_lockfile(tmp_path: Path, monkeypatch) -> None:
    _, workflow, packs = _setup(tmp_path, monkeypatch)
    root_asset = _asset(workflow, tmp_path, "root")
    dep_asset = _asset(workflow, tmp_path, "dep")

    dep = packs.create(AssetPackCreateRequest(name="Common", asset_ids=[dep_asset.id]))
    packs.release(dep.id, AssetPackReleaseRequest(version="1.0.0"))
    root = packs.create(
        AssetPackCreateRequest(
            name="Forest",
            asset_ids=[root_asset.id],
            dependencies=[AssetPackDependency(pack_id=dep.id)],
        )
    )
    release = packs.release(root.id, AssetPackReleaseRequest(version="1.0.0"))
    assert release.dependencies[0].pack_id == dep.id
    assert release.dependencies[0].version == "1.0.0"

    installation = packs.install(root.id, "1.0.0")
    assert installation.version == "1.0.0"
    assert installation.lock["packs"] == {dep.id: "1.0.0", root.id: "1.0.0"}
    assert root_asset.id in installation.lock["assets"]
    assert dep_asset.id in installation.lock["assets"]


def test_release_freezes_asset_version_and_updates_are_explicit(tmp_path: Path, monkeypatch) -> None:
    workspace, workflow, packs = _setup(tmp_path, monkeypatch)
    asset = _asset(workflow, tmp_path, "tree")
    pack = packs.create(AssetPackCreateRequest(name="Trees", asset_ids=[asset.id]))
    first = packs.release(pack.id, AssetPackReleaseRequest(version="1.0.0"))
    assert first.assets[0].version == 1
    packs.install(pack.id, "1.0.0")

    new_rel = f"library_versions/{asset.id}/v2.png"
    new_path = workspace / new_rel
    new_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (32, 32), (0, 255, 0, 255)).save(new_path)
    packs.library.add_version(asset.id, kind="manual_edit", image_path=new_rel, activate=True)
    second = packs.release(pack.id, AssetPackReleaseRequest(version="1.1.0"))
    assert second.assets[0].version == 2

    updates = {item.pack_id: item for item in packs.updates()}
    assert updates[pack.id].installed_version == "1.0.0"
    assert updates[pack.id].latest_version == "1.1.0"
    assert updates[pack.id].update_available is True

    exported = packs.export_release(pack.id, "1.0.0")
    with zipfile.ZipFile(exported.archive_path) as archive:
        doc = json.loads(archive.read("pack.json"))
        assert doc["release"]["version"] == "1.0.0"
        assert doc["release"]["assets"][0]["version"] == 1


def test_dependency_cycle_is_rejected_before_mutation(tmp_path: Path, monkeypatch) -> None:
    _, workflow, packs = _setup(tmp_path, monkeypatch)
    a_asset = _asset(workflow, tmp_path, "a")
    b_asset = _asset(workflow, tmp_path, "b")
    a = packs.create(AssetPackCreateRequest(name="A", asset_ids=[a_asset.id]))
    b = packs.create(
        AssetPackCreateRequest(
            name="B",
            asset_ids=[b_asset.id],
            dependencies=[AssetPackDependency(pack_id=a.id)],
        )
    )
    with pytest.raises(ValueError, match="cycle"):
        packs.update(a.id, AssetPackUpdateRequest(dependencies=[AssetPackDependency(pack_id=b.id)]))
    assert packs.get(a.id).dependencies == []
