from __future__ import annotations

import json
import shutil
import zipfile
from collections import deque
from pathlib import Path
from uuid import uuid4

import numpy as np
from PIL import Image, ImageOps

from app.asset_library_models import AssetRelationType, AssetReviewState, LibraryAsset
from app.asset_workflow_models import (
    AssetEditOperation,
    AssetEditRequest,
    AssetEditResult,
    AssetPackEngine,
    AssetPackExportRequest,
    AssetPackExportResult,
    HierarchyNode,
    LibrarySplitMode,
    LibrarySplitRequest,
    LibrarySplitResult,
)
from app.services.asset_library import AssetLibrary, LibraryAssetNotFoundError, utc_now
from app.services.pipeline import AssetSplitPipeline


class AssetLibraryWorkflowService:
    """Full reusable-asset workflow built on top of the global Asset Library.

    Files stay versioned and immutable. Editing creates a new Library version;
    hierarchy is represented by Asset Library relations; packs snapshot the active
    purchased/selected versions at export time.
    """

    def __init__(self, workspace: str | Path, pipeline: AssetSplitPipeline) -> None:
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.pipeline = pipeline
        self.library = AssetLibrary(self.workspace)
        self.import_root = self.workspace / "library_imports"
        self.version_root = self.workspace / "library_versions"
        self.state_root = self.workspace.parent / ".game_creater_state" / "asset_packs"
        self.import_root.mkdir(parents=True, exist_ok=True)
        self.version_root.mkdir(parents=True, exist_ok=True)
        self.state_root.mkdir(parents=True, exist_ok=True)

    def import_image(
        self,
        source_path: str | Path,
        *,
        name: str,
        category: str = "uncategorized",
        tags: list[str] | None = None,
        original_filename: str | None = None,
    ) -> LibraryAsset:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Asset name cannot be empty")
        asset_id = f"asset_{uuid4().hex[:16]}"
        asset_dir = self.import_root / asset_id
        asset_dir.mkdir(parents=True, exist_ok=False)

        with Image.open(source_path) as source:
            rgba = source.convert("RGBA")
        alpha = rgba.getchannel("A")
        alpha_array = np.asarray(alpha, dtype=np.uint8)
        binary = Image.fromarray(np.where(alpha_array > 0, 255, 0).astype(np.uint8))

        image_rel = self._relative(asset_dir / "source.png")
        mask_rel = self._relative(asset_dir / "mask.png")
        alpha_rel = self._relative(asset_dir / "alpha.png")
        rgba.save(self.workspace / image_rel, format="PNG")
        binary.save(self.workspace / mask_rel, format="PNG")
        alpha.save(self.workspace / alpha_rel, format="PNG")

        now = utc_now()
        provenance = {
            "source": "image_import",
            "original_filename": original_filename,
            "imported_at": now,
        }
        with self.library._connect() as db:
            db.execute(
                """
                INSERT INTO assets (
                    id, scene_id, scene_asset_id, project_id, name, category,
                    review_state, favorite, confidence, asset_score, width, height,
                    image_path, mask_path, alpha_path, source_image_path,
                    completed, active_version, notes, provenance_json,
                    created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    asset_id,
                    "library_import",
                    asset_id,
                    None,
                    clean_name,
                    category.strip() or "uncategorized",
                    AssetReviewState.NEEDS_REVIEW.value,
                    0,
                    1.0,
                    1.0,
                    rgba.width,
                    rgba.height,
                    image_rel,
                    mask_rel,
                    alpha_rel,
                    image_rel,
                    0,
                    1,
                    None,
                    json.dumps(provenance, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            db.execute(
                """
                INSERT INTO asset_versions(
                    asset_id,version,kind,image_path,mask_path,alpha_path,
                    metadata_json,created_at
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    asset_id,
                    1,
                    "imported",
                    image_rel,
                    mask_rel,
                    alpha_rel,
                    json.dumps({"original_filename": original_filename}, ensure_ascii=False),
                    now,
                ),
            )
            self.library._replace_tags(db, asset_id, tags or [])
        return self.library.get(asset_id)

    def split(self, asset_id: str, request: LibrarySplitRequest) -> LibrarySplitResult:
        parent = self.library.get(asset_id)
        image_path = self.workspace / parent.image_path
        if not image_path.is_file():
            raise ValueError("Active asset image is missing")

        if request.mode == LibrarySplitMode.AI_SCENE:
            prompts = [item.strip() for item in request.prompts if item.strip()]
            if not prompts:
                raise ValueError("AI scene split requires at least one detection prompt")
            manifest = self.pipeline.run(image_path, prompts)
            child_ids = [asset.library_asset_id for asset in manifest.assets if asset.library_asset_id]
            self.add_children(asset_id, child_ids)
            return LibrarySplitResult(
                parent_asset_id=asset_id,
                mode=request.mode,
                child_asset_ids=child_ids,
                scene_id=manifest.scene_id,
                metadata={"prompts": prompts, "asset_count": len(child_ids)},
            )

        with Image.open(image_path) as source:
            rgba = source.convert("RGBA")

        crops: list[tuple[tuple[int, int, int, int], str]] = []
        if request.mode == LibrarySplitMode.GRID:
            for row in range(request.rows):
                y1 = round(row * rgba.height / request.rows)
                y2 = round((row + 1) * rgba.height / request.rows)
                for column in range(request.columns):
                    x1 = round(column * rgba.width / request.columns)
                    x2 = round((column + 1) * rgba.width / request.columns)
                    crops.append(((x1, y1, x2, y2), f"r{row + 1}_c{column + 1}"))
        elif request.mode == LibrarySplitMode.ALPHA_COMPONENTS:
            alpha = np.asarray(rgba.getchannel("A"), dtype=np.uint8) > 0
            for index, bbox in enumerate(self._component_boxes(alpha, request.min_area), start=1):
                crops.append((bbox, f"part_{index:03d}"))
        else:
            raise ValueError(f"Unsupported split mode: {request.mode}")

        child_ids: list[str] = []
        prefix = (request.name_prefix or parent.name).strip() or parent.name
        category = (request.category or parent.category).strip() or "uncategorized"
        for bbox, suffix in crops:
            crop = rgba.crop(bbox)
            if crop.width < 1 or crop.height < 1:
                continue
            if not np.asarray(crop.getchannel("A"), dtype=np.uint8).any():
                continue
            child = self._create_child_asset(
                parent,
                crop,
                name=f"{prefix}_{suffix}",
                category=category,
                bbox=bbox,
                split_mode=request.mode.value,
            )
            child_ids.append(child.id)

        if not child_ids:
            raise ValueError("Split produced no non-empty child assets")
        self.add_children(asset_id, child_ids)
        return LibrarySplitResult(
            parent_asset_id=asset_id,
            mode=request.mode,
            child_asset_ids=child_ids,
            metadata={"asset_count": len(child_ids)},
        )

    def add_children(self, parent_asset_id: str, child_asset_ids: list[str]) -> None:
        self.library.get(parent_asset_id)
        for child_id in child_asset_ids:
            self.library.add_relation(parent_asset_id, child_id, AssetRelationType.PARENT_OF)
            self.library.add_relation(child_id, parent_asset_id, AssetRelationType.PART_OF)

    def remove_child(self, parent_asset_id: str, child_asset_id: str) -> None:
        with self.library._connect() as db:
            db.execute(
                "DELETE FROM asset_relations WHERE source_asset_id=? AND target_asset_id=? AND relation_type=?",
                (parent_asset_id, child_asset_id, AssetRelationType.PARENT_OF.value),
            )
            db.execute(
                "DELETE FROM asset_relations WHERE source_asset_id=? AND target_asset_id=? AND relation_type=?",
                (child_asset_id, parent_asset_id, AssetRelationType.PART_OF.value),
            )

    def hierarchy(self, asset_id: str, *, depth: int = 8) -> HierarchyNode:
        depth = max(0, min(int(depth), 32))
        return self._hierarchy_node(asset_id, depth, set())

    def edit(self, asset_id: str, request: AssetEditRequest) -> AssetEditResult:
        asset = self.library.get(asset_id)
        image = self._load_rgba(asset.image_path)
        mask = self._load_layer(asset.mask_path, image.size, binary=True)
        alpha = self._load_layer(asset.alpha_path, image.size, binary=False) if asset.alpha_path else image.getchannel("A")

        image, mask, alpha = self._apply_edit(image, mask, alpha, request)
        token = uuid4().hex[:10]
        target = self.version_root / asset_id
        target.mkdir(parents=True, exist_ok=True)
        image_rel = self._relative(target / f"{token}_{request.operation.value}.png")
        mask_rel = self._relative(target / f"{token}_{request.operation.value}_mask.png")
        alpha_rel = self._relative(target / f"{token}_{request.operation.value}_alpha.png")
        image.putalpha(alpha)
        image.save(self.workspace / image_rel, format="PNG")
        mask.save(self.workspace / mask_rel, format="PNG")
        alpha.save(self.workspace / alpha_rel, format="PNG")

        version = self.library.add_version(
            asset_id,
            kind=f"edit:{request.operation.value}",
            image_path=image_rel,
            mask_path=mask_rel,
            alpha_path=alpha_rel,
            metadata={"operation": request.operation.value, "request": request.model_dump(mode="json")},
            activate=request.activate,
        )
        if request.activate:
            with self.library._connect() as db:
                db.execute(
                    "UPDATE assets SET width=?,height=?,updated_at=? WHERE id=?",
                    (image.width, image.height, utc_now(), asset_id),
                )
        return AssetEditResult(
            asset_id=asset_id,
            operation=request.operation,
            version=version.version,
            image_path=image_rel,
            mask_path=mask_rel,
            alpha_path=alpha_rel,
            width=image.width,
            height=image.height,
        )

    def export_pack(self, request: AssetPackExportRequest) -> AssetPackExportResult:
        clean_name = request.name.strip()
        if not clean_name:
            raise ValueError("Pack name cannot be empty")
        asset_ids = list(dict.fromkeys(request.asset_ids))
        if request.collection_id:
            asset_ids.extend(self._collection_asset_ids(request.collection_id))
            asset_ids = list(dict.fromkeys(asset_ids))
        if not asset_ids:
            raise ValueError("Asset pack requires at least one asset or Collection")

        assets = [self.library.get(asset_id) for asset_id in asset_ids]
        pack_id = f"pack_{uuid4().hex[:12]}"
        pack_dir = self.state_root / pack_id
        pack_dir.mkdir(parents=True, exist_ok=False)

        if request.engine == AssetPackEngine.GENERIC:
            content_root = pack_dir / "generic"
        elif request.engine == AssetPackEngine.GODOT4:
            content_root = pack_dir / "godot4"
        else:
            content_root = pack_dir / "unity2d" / "Assets" / "GameCreaterPack"
        content_root.mkdir(parents=True, exist_ok=True)

        manifest_assets: list[dict] = []
        for asset in assets:
            entry = self._copy_pack_asset(content_root, asset, request)
            if request.include_hierarchy:
                entry["children"] = self._direct_children(asset.id)
                entry["parents"] = self._direct_parents(asset.id)
            manifest_assets.append(entry)

        manifest = {
            "schema": "game-creater/asset-pack/v1",
            "pack_id": pack_id,
            "name": clean_name,
            "engine": request.engine.value,
            "created_at": utc_now(),
            "asset_count": len(manifest_assets),
            "assets": manifest_assets,
        }
        manifest_path = pack_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        if request.engine == AssetPackEngine.GODOT4:
            self._write_godot_files(pack_dir / "godot4", manifest_assets)
        elif request.engine == AssetPackEngine.UNITY2D:
            self._write_unity_files(pack_dir / "unity2d", manifest)

        archive_path = self.state_root / f"{pack_id}.zip"
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(pack_dir.rglob("*")):
                if path.is_file():
                    archive.write(path, arcname=path.relative_to(pack_dir))

        return AssetPackExportResult(
            pack_id=pack_id,
            name=clean_name,
            engine=request.engine,
            asset_count=len(assets),
            archive_path=str(archive_path),
            download_url=f"/api/v1/library/packs/{pack_id}/download",
            manifest_path=str(manifest_path),
        )

    def pack_archive(self, pack_id: str) -> Path:
        if not pack_id.startswith("pack_") or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for ch in pack_id):
            raise ValueError("Invalid pack id")
        path = self.state_root / f"{pack_id}.zip"
        if not path.is_file():
            raise FileNotFoundError(pack_id)
        return path

    def _create_child_asset(
        self,
        parent: LibraryAsset,
        rgba: Image.Image,
        *,
        name: str,
        category: str,
        bbox: tuple[int, int, int, int],
        split_mode: str,
    ) -> LibraryAsset:
        asset_id = f"asset_{uuid4().hex[:16]}"
        asset_dir = self.import_root / asset_id
        asset_dir.mkdir(parents=True, exist_ok=False)
        alpha = rgba.getchannel("A")
        binary = Image.fromarray(np.where(np.asarray(alpha, dtype=np.uint8) > 0, 255, 0).astype(np.uint8))
        image_rel = self._relative(asset_dir / "source.png")
        mask_rel = self._relative(asset_dir / "mask.png")
        alpha_rel = self._relative(asset_dir / "alpha.png")
        rgba.save(self.workspace / image_rel, format="PNG")
        binary.save(self.workspace / mask_rel, format="PNG")
        alpha.save(self.workspace / alpha_rel, format="PNG")
        now = utc_now()
        provenance = {
            "source": "library_split",
            "parent_asset_id": parent.id,
            "parent_version": parent.active_version,
            "split_mode": split_mode,
            "source_bbox": {"x1": bbox[0], "y1": bbox[1], "x2": bbox[2], "y2": bbox[3]},
        }
        with self.library._connect() as db:
            db.execute(
                """
                INSERT INTO assets(
                    id,scene_id,scene_asset_id,project_id,name,category,review_state,
                    favorite,confidence,asset_score,width,height,image_path,mask_path,
                    alpha_path,source_image_path,completed,active_version,notes,
                    provenance_json,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    asset_id,"library_split",asset_id,parent.project_id,name,category,
                    AssetReviewState.NEEDS_REVIEW.value,0,1.0,parent.asset_score,
                    rgba.width,rgba.height,image_rel,mask_rel,alpha_rel,parent.image_path,
                    0,1,None,json.dumps(provenance,ensure_ascii=False),now,now,
                ),
            )
            db.execute(
                "INSERT INTO asset_versions(asset_id,version,kind,image_path,mask_path,alpha_path,metadata_json,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (asset_id,1,"split",image_rel,mask_rel,alpha_rel,json.dumps(provenance,ensure_ascii=False),now),
            )
        return self.library.get(asset_id)

    def _hierarchy_node(self, asset_id: str, depth: int, visited: set[str]) -> HierarchyNode:
        asset = self.library.get(asset_id)
        if depth == 0 or asset_id in visited:
            return HierarchyNode(asset_id=asset.id,name=asset.name,category=asset.category,image_path=asset.image_path)
        next_visited = set(visited)
        next_visited.add(asset_id)
        children = [self._hierarchy_node(child_id, depth - 1, next_visited) for child_id in self._direct_children(asset_id) if child_id not in next_visited]
        return HierarchyNode(asset_id=asset.id,name=asset.name,category=asset.category,image_path=asset.image_path,children=children)

    def _direct_children(self, asset_id: str) -> list[str]:
        return [
            row["target_asset_id"] for row in self.library.relations(asset_id)
            if row["source_asset_id"] == asset_id and row["relation_type"] == AssetRelationType.PARENT_OF.value
        ]

    def _direct_parents(self, asset_id: str) -> list[str]:
        return [
            row["target_asset_id"] for row in self.library.relations(asset_id)
            if row["source_asset_id"] == asset_id and row["relation_type"] == AssetRelationType.PART_OF.value
        ]

    def _collection_asset_ids(self, collection_id: str) -> list[str]:
        with self.library._connect() as db:
            exists = db.execute("SELECT id FROM collections WHERE id=?", (collection_id,)).fetchone()
            if exists is None:
                raise ValueError("Collection not found")
            rows = db.execute("SELECT asset_id FROM collection_assets WHERE collection_id=? ORDER BY asset_id", (collection_id,)).fetchall()
        return [row["asset_id"] for row in rows]

    def _copy_pack_asset(self, root: Path, asset: LibraryAsset, request: AssetPackExportRequest) -> dict:
        assets_dir = root / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        image_name = f"{asset.id}.png"
        shutil.copy2(self.workspace / asset.image_path, assets_dir / image_name)
        mask_name = None
        alpha_name = None
        if request.include_masks and asset.mask_path and (self.workspace / asset.mask_path).is_file():
            mask_name = f"{asset.id}_mask.png"
            shutil.copy2(self.workspace / asset.mask_path, assets_dir / mask_name)
        if request.include_alpha and asset.alpha_path and (self.workspace / asset.alpha_path).is_file():
            alpha_name = f"{asset.id}_alpha.png"
            shutil.copy2(self.workspace / asset.alpha_path, assets_dir / alpha_name)
        return {
            "id": asset.id,
            "name": asset.name,
            "category": asset.category,
            "subcategory": asset.subcategory,
            "tags": asset.tags,
            "version": asset.active_version,
            "width": asset.width,
            "height": asset.height,
            "image": f"assets/{image_name}",
            "mask": f"assets/{mask_name}" if mask_name else None,
            "alpha": f"assets/{alpha_name}" if alpha_name else None,
            "review_state": asset.review_state.value,
            "provenance": asset.provenance,
        }

    @staticmethod
    def _write_godot_files(root: Path, assets: list[dict]) -> None:
        resources = root / "resources"
        resources.mkdir(parents=True, exist_ok=True)
        (root / "README.md").write_text("Copy this folder into a Godot 4 project. PNG files import automatically; .tres files expose AtlasTexture resources.\n", encoding="utf-8")
        for asset in assets:
            safe_id = asset["id"].replace("-", "_")
            tres = (
                "[gd_resource type=\"AtlasTexture\" load_steps=2 format=3]\n\n"
                f"[ext_resource type=\"Texture2D\" path=\"res://assets/{asset['id']}.png\" id=\"1_tex\"]\n\n"
                "[resource]\n"
                "atlas = ExtResource(\"1_tex\")\n"
                f"region = Rect2(0, 0, {asset['width']}, {asset['height']})\n"
            )
            (resources / f"{safe_id}.tres").write_text(tres, encoding="utf-8")

    @staticmethod
    def _write_unity_files(root: Path, manifest: dict) -> None:
        pack_root = root / "Assets" / "GameCreaterPack"
        pack_root.mkdir(parents=True, exist_ok=True)
        (pack_root / "GameCreaterPack.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        editor = pack_root / "Editor"
        editor.mkdir(parents=True, exist_ok=True)
        script = r'''using UnityEditor;
using UnityEngine;

public static class GameCreaterPackImporter
{
    [MenuItem("Game Creater/Configure Imported Asset Pack")]
    public static void Configure()
    {
        var guids = AssetDatabase.FindAssets("t:Texture2D", new[] { "Assets/GameCreaterPack/assets" });
        foreach (var guid in guids)
        {
            var path = AssetDatabase.GUIDToAssetPath(guid);
            if (AssetImporter.GetAtPath(path) is TextureImporter importer)
            {
                importer.textureType = TextureImporterType.Sprite;
                importer.spriteImportMode = SpriteImportMode.Single;
                importer.spritePixelsPerUnit = 100f;
                importer.alphaIsTransparency = true;
                importer.mipmapEnabled = false;
                importer.SaveAndReimport();
            }
        }
        AssetDatabase.Refresh();
        Debug.Log($"Game Creater: configured {guids.Length} Sprite textures.");
    }
}
'''
        (editor / "GameCreaterPackImporter.cs").write_text(script, encoding="utf-8")

    @staticmethod
    def _component_boxes(mask: np.ndarray, min_area: int) -> list[tuple[int, int, int, int]]:
        height, width = mask.shape
        visited = np.zeros_like(mask, dtype=bool)
        boxes: list[tuple[int, int, int, int, int]] = []
        for y in range(height):
            for x in range(width):
                if not mask[y, x] or visited[y, x]:
                    continue
                queue = deque([(x, y)])
                visited[y, x] = True
                min_x = max_x = x
                min_y = max_y = y
                area = 0
                while queue:
                    cx, cy = queue.popleft()
                    area += 1
                    min_x, max_x = min(min_x, cx), max(max_x, cx)
                    min_y, max_y = min(min_y, cy), max(max_y, cy)
                    for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                        if 0 <= nx < width and 0 <= ny < height and mask[ny, nx] and not visited[ny, nx]:
                            visited[ny, nx] = True
                            queue.append((nx, ny))
                if area >= min_area:
                    boxes.append((min_x, min_y, max_x + 1, max_y + 1, area))
        boxes.sort(key=lambda item: (-item[4], item[1], item[0]))
        return [(x1, y1, x2, y2) for x1, y1, x2, y2, _ in boxes]

    def _apply_edit(self, image: Image.Image, mask: Image.Image, alpha: Image.Image, request: AssetEditRequest) -> tuple[Image.Image, Image.Image, Image.Image]:
        op = request.operation
        if op == AssetEditOperation.CROP:
            if request.rect is None:
                raise ValueError("Crop requires rect")
            box = (request.rect.x1, request.rect.y1, request.rect.x2, request.rect.y2)
            if not (0 <= box[0] < box[2] <= image.width and 0 <= box[1] < box[3] <= image.height):
                raise ValueError("Crop rectangle is outside the asset")
            return image.crop(box), mask.crop(box), alpha.crop(box)
        if op == AssetEditOperation.RESIZE:
            width = request.width or image.width
            height = request.height or image.height
            return (
                image.resize((width, height), Image.Resampling.LANCZOS),
                mask.resize((width, height), Image.Resampling.NEAREST),
                alpha.resize((width, height), Image.Resampling.LANCZOS),
            )
        if op == AssetEditOperation.TRIM_ALPHA:
            bbox = alpha.getbbox() or mask.getbbox()
            if bbox is None:
                raise ValueError("Cannot trim an empty asset")
            return image.crop(bbox), mask.crop(bbox), alpha.crop(bbox)
        if op == AssetEditOperation.FLIP_HORIZONTAL:
            return tuple(layer.transpose(Image.Transpose.FLIP_LEFT_RIGHT) for layer in (image, mask, alpha))
        if op == AssetEditOperation.FLIP_VERTICAL:
            return tuple(layer.transpose(Image.Transpose.FLIP_TOP_BOTTOM) for layer in (image, mask, alpha))
        if op == AssetEditOperation.ROTATE_90:
            method = Image.Transpose.ROTATE_270 if request.clockwise else Image.Transpose.ROTATE_90
            return tuple(layer.transpose(method) for layer in (image, mask, alpha))
        if op == AssetEditOperation.PAD:
            return tuple(ImageOps.expand(layer, border=request.padding, fill=(0, 0, 0, 0) if layer.mode == "RGBA" else 0) for layer in (image, mask, alpha))
        raise ValueError(f"Unsupported edit operation: {op}")

    def _load_rgba(self, relative: str) -> Image.Image:
        path = self.workspace / relative
        if not path.is_file():
            raise ValueError(f"Asset file is missing: {relative}")
        return Image.open(path).convert("RGBA")

    def _load_layer(self, relative: str | None, size: tuple[int, int], *, binary: bool) -> Image.Image:
        if not relative:
            return Image.new("L", size, 255)
        path = self.workspace / relative
        if not path.is_file():
            return Image.new("L", size, 255)
        layer = Image.open(path).convert("L")
        if layer.size != size:
            layer = layer.resize(size, Image.Resampling.NEAREST if binary else Image.Resampling.LANCZOS)
        if binary:
            layer = Image.fromarray(np.where(np.asarray(layer, dtype=np.uint8) > 0, 255, 0).astype(np.uint8))
        return layer

    def _relative(self, path: Path) -> str:
        return str(path.relative_to(self.workspace)).replace("\\", "/")
