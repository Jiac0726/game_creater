from __future__ import annotations

import json
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

from app.asset_workflow_models import (
    AssetEditOperation,
    AssetEditRequest,
    AssetPackEngine,
    AssetPackExportRequest,
    LibrarySplitMode,
    LibrarySplitRequest,
)
from app.services.asset_library_workflow import AssetLibraryWorkflowService
from app.services.pipeline import AssetSplitPipeline


def _service(tmp_path: Path, monkeypatch) -> AssetLibraryWorkflowService:
    monkeypatch.setenv("GAME_CREATER_MODE", "mock")
    workspace = tmp_path / "workspace"
    return AssetLibraryWorkflowService(workspace, AssetSplitPipeline(workspace))


def _transparent_sheet(path: Path) -> None:
    image = Image.new("RGBA", (120, 80), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 8, 45, 45), fill=(255, 80, 60, 255))
    draw.rectangle((72, 20, 110, 68), fill=(60, 160, 255, 255))
    image.save(path)


def test_import_image_creates_stable_library_asset_and_version(tmp_path: Path, monkeypatch) -> None:
    service = _service(tmp_path, monkeypatch)
    source = tmp_path / "tree.png"
    Image.new("RGBA", (64, 48), (20, 140, 40, 200)).save(source)

    asset = service.import_image(
        source,
        name="Tree",
        category="vegetation",
        tags=["forest", "tree"],
        original_filename="tree.png",
    )

    assert asset.id.startswith("asset_")
    assert asset.scene_id == "library_import"
    assert asset.category == "vegetation"
    assert asset.tags == ["forest", "tree"]
    assert asset.active_version == 1
    assert asset.width == 64 and asset.height == 48
    assert (service.workspace / asset.image_path).is_file()
    assert (service.workspace / asset.mask_path).is_file()
    assert (service.workspace / asset.alpha_path).is_file()
    versions = service.library.list_versions(asset.id)
    assert len(versions) == 1
    assert versions[0].kind == "imported"
    assert asset.provenance["source"] == "image_import"


def test_grid_split_builds_parent_child_hierarchy(tmp_path: Path, monkeypatch) -> None:
    service = _service(tmp_path, monkeypatch)
    source = tmp_path / "sheet.png"
    Image.new("RGBA", (100, 60), (255, 255, 255, 255)).save(source)
    parent = service.import_image(source, name="Props Sheet", category="props")

    result = service.split(
        parent.id,
        LibrarySplitRequest(mode=LibrarySplitMode.GRID, rows=2, columns=2),
    )

    assert len(result.child_asset_ids) == 4
    tree = service.hierarchy(parent.id)
    assert tree.asset_id == parent.id
    assert {child.asset_id for child in tree.children} == set(result.child_asset_ids)
    for child_id in result.child_asset_ids:
        child = service.library.get(child_id)
        assert child.width == 50
        assert child.height == 30
        assert child.provenance["parent_asset_id"] == parent.id


def test_alpha_component_split_detects_disconnected_sprites(tmp_path: Path, monkeypatch) -> None:
    service = _service(tmp_path, monkeypatch)
    source = tmp_path / "components.png"
    _transparent_sheet(source)
    parent = service.import_image(source, name="Sprite Sheet", category="props")

    result = service.split(
        parent.id,
        LibrarySplitRequest(mode=LibrarySplitMode.ALPHA_COMPONENTS, min_area=50),
    )

    assert len(result.child_asset_ids) == 2
    sizes = sorted((service.library.get(item).width, service.library.get(item).height) for item in result.child_asset_ids)
    assert sizes[0][0] > 20 and sizes[0][1] > 20
    assert sizes[1][0] > 20 and sizes[1][1] > 20


def test_asset_edit_is_non_destructive_and_creates_active_version(tmp_path: Path, monkeypatch) -> None:
    service = _service(tmp_path, monkeypatch)
    source = tmp_path / "edit.png"
    image = Image.new("RGBA", (80, 60), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((20, 10, 59, 49), fill=(255, 255, 255, 255))
    image.save(source)
    asset = service.import_image(source, name="Editable", category="prop")
    original_path = service.workspace / asset.image_path
    original_bytes = original_path.read_bytes()

    result = service.edit(
        asset.id,
        AssetEditRequest(operation=AssetEditOperation.TRIM_ALPHA),
    )

    assert result.version == 2
    assert result.width == 40
    assert result.height == 40
    assert original_path.read_bytes() == original_bytes
    updated = service.library.get(asset.id)
    assert updated.active_version == 2
    assert updated.image_path == result.image_path
    versions = service.library.list_versions(asset.id)
    assert [item.version for item in versions] == [2, 1]
    assert versions[0].kind == "edit:trim_alpha"


def test_generic_pack_exports_assets_manifest_and_hierarchy(tmp_path: Path, monkeypatch) -> None:
    service = _service(tmp_path, monkeypatch)
    source = tmp_path / "pack.png"
    Image.new("RGBA", (80, 40), (255, 255, 255, 255)).save(source)
    parent = service.import_image(source, name="Pack Root", category="props")
    split = service.split(parent.id, LibrarySplitRequest(mode=LibrarySplitMode.GRID, rows=1, columns=2))

    exported = service.export_pack(
        AssetPackExportRequest(
            name="Starter Props",
            asset_ids=[parent.id, *split.child_asset_ids],
            engine=AssetPackEngine.GENERIC,
        )
    )

    archive = Path(exported.archive_path)
    assert archive.is_file()
    with zipfile.ZipFile(archive) as bundle:
        names = set(bundle.namelist())
        assert "manifest.json" in names
        assert any(name.startswith("generic/assets/") and name.endswith(".png") for name in names)
        manifest = json.loads(bundle.read("manifest.json").decode("utf-8"))
        root = next(item for item in manifest["assets"] if item["id"] == parent.id)
        assert set(root["children"]) == set(split.child_asset_ids)
        assert manifest["asset_count"] == 3


def test_godot_and_unity_packs_include_engine_recognizable_files(tmp_path: Path, monkeypatch) -> None:
    service = _service(tmp_path, monkeypatch)
    source = tmp_path / "engine.png"
    Image.new("RGBA", (32, 32), (255, 255, 255, 255)).save(source)
    asset = service.import_image(source, name="Engine Prop", category="prop")

    godot = service.export_pack(
        AssetPackExportRequest(name="Godot Props", asset_ids=[asset.id], engine=AssetPackEngine.GODOT4)
    )
    with zipfile.ZipFile(godot.archive_path) as bundle:
        names = set(bundle.namelist())
        assert f"godot4/assets/{asset.id}.png" in names
        assert f"godot4/resources/{asset.id}.tres" in names
        assert "godot4/README.md" in names

    unity = service.export_pack(
        AssetPackExportRequest(name="Unity Props", asset_ids=[asset.id], engine=AssetPackEngine.UNITY2D)
    )
    with zipfile.ZipFile(unity.archive_path) as bundle:
        names = set(bundle.namelist())
        assert f"unity2d/Assets/GameCreaterPack/assets/{asset.id}.png" in names
        assert "unity2d/Assets/GameCreaterPack/Editor/GameCreaterPackImporter.cs" in names
        assert "unity2d/Assets/GameCreaterPack/GameCreaterPack.json" in names
