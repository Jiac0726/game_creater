from __future__ import annotations

from pathlib import Path

from app.models import AssetRecord, BBox, SceneManifest
from app.services.library_index import LibraryIndex


def _write_scene(root: Path, scene_id: str, *, prompt: str, category: str) -> None:
    scene_dir = root / scene_id
    scene_dir.mkdir(parents=True)
    manifest = SceneManifest(
        scene_id=scene_id,
        source_image="source.png",
        width=640,
        height=480,
        mode="mock",
        prompts=[prompt],
        assets=[
            AssetRecord(
                id="asset_0001",
                label="house",
                category=category,
                bbox=BBox(x1=1, y1=2, x2=30, y2=40),
                image="assets/house.png",
                mask="masks/house.png",
            )
        ],
    )
    (scene_dir / "scene.json").write_text(
        manifest.model_dump_json(indent=2),
        encoding="utf-8",
    )


def test_library_index_lists_valid_scenes_and_aggregates_categories(tmp_path: Path) -> None:
    _write_scene(tmp_path, "aaaaaaaaaaaa", prompt="forest village", category="building")
    _write_scene(tmp_path, "bbbbbbbbbbbb", prompt="cave", category="terrain")
    (tmp_path / "exports").mkdir()
    (tmp_path / "not-a-scene").mkdir()

    result = LibraryIndex(tmp_path).build()

    assert result["asset_count"] == 2
    assert result["category_counts"] == {"building": 1, "terrain": 1}
    assert {scene["scene_id"] for scene in result["scenes"]} == {
        "aaaaaaaaaaaa",
        "bbbbbbbbbbbb",
    }
    assert {scene["title"] for scene in result["scenes"]} == {
        "forest village",
        "cave",
    }
    assert {scene["relative_path"] for scene in result["scenes"]} == {
        "aaaaaaaaaaaa/scene.json",
        "bbbbbbbbbbbb/scene.json",
    }


def test_library_index_ignores_invalid_manifest(tmp_path: Path) -> None:
    invalid_scene = tmp_path / "cccccccccccc"
    invalid_scene.mkdir()
    (invalid_scene / "scene.json").write_text("not json", encoding="utf-8")

    assert LibraryIndex(tmp_path).build() == {
        "scenes": [],
        "asset_count": 0,
        "category_counts": {},
    }


def test_library_index_rejects_paths_outside_project_workspace(tmp_path: Path) -> None:
    _write_scene(tmp_path, "dddddddddddd", prompt="unsafe", category="prop")
    manifest_path = tmp_path / "dddddddddddd" / "scene.json"
    manifest = SceneManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    manifest.assets[0] = manifest.assets[0].model_copy(
        update={"image": "../../outside.png"}
    )
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    assert LibraryIndex(tmp_path).build()["scenes"] == []
