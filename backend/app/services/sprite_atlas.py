from __future__ import annotations

import json
import re
import shutil
import zipfile
from pathlib import Path
from uuid import uuid4

from PIL import Image
from rectpack import newPacker

from app.services.asset_library import AssetLibrary
from app.sprite_atlas_models import (
    AtlasBuildRequest,
    AtlasBuildResult,
    AtlasEngine,
    AtlasManifest,
    AtlasPage,
    AtlasSpriteEntry,
)


class SpriteAtlasService:
    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace)
        self.library = AssetLibrary(self.workspace)
        self.state_root = self.workspace.parent / ".game_creater_state" / "atlas_exports"
        self.state_root.mkdir(parents=True, exist_ok=True)

    def build(self, request: AtlasBuildRequest) -> AtlasBuildResult:
        name = request.name.strip()
        if not name:
            raise ValueError("Atlas name cannot be empty")
        if request.power_of_two and (not self._is_power_of_two(request.max_width) or not self._is_power_of_two(request.max_height)):
            raise ValueError("max_width and max_height must be powers of two when power_of_two=true")

        asset_ids = list(dict.fromkeys(request.asset_ids))
        prepared: dict[str, dict] = {}
        for asset_id in asset_ids:
            asset = self.library.get(asset_id)
            path = self.workspace / asset.image_path
            if not path.is_file():
                raise FileNotFoundError(path)
            with Image.open(path) as source:
                rgba = source.convert("RGBA")
            source_width, source_height = rgba.size
            trim_x = trim_y = 0
            if request.trim_transparent:
                bbox = rgba.getchannel("A").getbbox()
                if bbox is None:
                    raise ValueError(f"Asset {asset_id} is fully transparent")
                trim_x, trim_y, x2, y2 = bbox
                rgba = rgba.crop(bbox)
            width, height = rgba.size
            packed_w = width + request.padding * 2
            packed_h = height + request.padding * 2
            if packed_w > request.max_width or packed_h > request.max_height:
                raise ValueError(f"Asset {asset_id} ({packed_w}x{packed_h}) exceeds atlas max size")
            prepared[asset_id] = {
                "asset": asset,
                "image": rgba,
                "width": width,
                "height": height,
                "source_width": source_width,
                "source_height": source_height,
                "trim_x": trim_x,
                "trim_y": trim_y,
                "packed_w": packed_w,
                "packed_h": packed_h,
            }

        packer = newPacker(rotation=False)
        for asset_id, item in prepared.items():
            packer.add_rect(item["packed_w"], item["packed_h"], rid=asset_id)
        packer.add_bin(request.max_width, request.max_height, count=max(1, len(prepared)))
        packer.pack()
        placements = packer.rect_list()
        if len(placements) != len(prepared):
            raise RuntimeError("rectpack could not place every sprite")

        atlas_id = f"atlas_{uuid4().hex[:12]}"
        root = self.state_root / atlas_id
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)

        by_page: dict[int, list[tuple[int, int, int, int, str]]] = {}
        for page, x, y, w, h, rid in placements:
            by_page.setdefault(int(page), []).append((int(x), int(y), int(w), int(h), str(rid)))

        pages: list[AtlasPage] = []
        entries: list[AtlasSpriteEntry] = []
        for page_index in sorted(by_page):
            placement_list = by_page[page_index]
            used_w = max(x + w for x, y, w, h, rid in placement_list)
            used_h = max(y + h for x, y, w, h, rid in placement_list)
            page_w = self._next_power_of_two(used_w) if request.power_of_two else used_w
            page_h = self._next_power_of_two(used_h) if request.power_of_two else used_h
            page_w = max(1, min(page_w, request.max_width))
            page_h = max(1, min(page_h, request.max_height))
            canvas = Image.new("RGBA", (page_w, page_h), (0, 0, 0, 0))
            for x, y, packed_w, packed_h, asset_id in placement_list:
                item = prepared[asset_id]
                px = x + request.padding
                py = y + request.padding
                canvas.alpha_composite(item["image"], (px, py))
                entries.append(
                    AtlasSpriteEntry(
                        asset_id=asset_id,
                        asset_name=item["asset"].name,
                        page=page_index,
                        x=px,
                        y=py,
                        width=item["width"],
                        height=item["height"],
                        source_width=item["source_width"],
                        source_height=item["source_height"],
                        trim_x=item["trim_x"],
                        trim_y=item["trim_y"],
                    )
                )
            filename = f"atlas_{page_index}.png"
            canvas.save(root / filename, format="PNG", optimize=True)
            pages.append(AtlasPage(index=page_index, filename=filename, width=page_w, height=page_h, sprite_count=len(placement_list)))

        manifest = AtlasManifest(
            atlas_id=atlas_id,
            name=name,
            engine=request.engine,
            padding=request.padding,
            trim_transparent=request.trim_transparent,
            power_of_two=request.power_of_two,
            pages=pages,
            sprites=sorted(entries, key=lambda item: asset_ids.index(item.asset_id)),
        )
        manifest_path = root / "atlas.json"
        manifest_path.write_text(json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")

        if request.engine == AtlasEngine.GODOT4:
            self._write_godot(root, manifest)
        elif request.engine == AtlasEngine.UNITY2D:
            self._write_unity(root, manifest)

        archive = self.state_root / f"{atlas_id}.zip"
        archive.unlink(missing_ok=True)
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    output.write(path, path.relative_to(root))
        return AtlasBuildResult(
            atlas_id=atlas_id,
            name=name,
            engine=request.engine,
            page_count=len(pages),
            sprite_count=len(entries),
            archive_path=str(archive),
            manifest_path=str(manifest_path),
            download_url=f"/api/v1/library/atlases/{atlas_id}/download",
        )

    def download_path(self, atlas_id: str) -> Path:
        if not re.fullmatch(r"atlas_[0-9a-f]{12}", atlas_id):
            raise ValueError("Invalid atlas id")
        path = self.state_root / f"{atlas_id}.zip"
        if not path.is_file():
            raise FileNotFoundError(path)
        return path

    def _write_godot(self, root: Path, manifest: AtlasManifest) -> None:
        godot = root / "godot4"
        resources = godot / "resources"
        resources.mkdir(parents=True, exist_ok=True)
        for page in manifest.pages:
            shutil.copy2(root / page.filename, godot / page.filename)
        for sprite in manifest.sprites:
            page = next(item for item in manifest.pages if item.index == sprite.page)
            text = (
                '[gd_resource type="AtlasTexture" load_steps=2 format=3]\n\n'
                f'[ext_resource type="Texture2D" path="res://{page.filename}" id="1_tex"]\n\n'
                '[resource]\n'
                'atlas = ExtResource("1_tex")\n'
                f'region = Rect2({sprite.x}, {sprite.y}, {sprite.width}, {sprite.height})\n'
                f'filter_clip = true\n'
            )
            (resources / f"{sprite.asset_id}.tres").write_text(text, encoding="utf-8")
        (godot / "README.md").write_text(
            "Copy the godot4 directory contents into a Godot project. Each resources/*.tres is a native AtlasTexture pointing at an atlas page.\n",
            encoding="utf-8",
        )

    def _write_unity(self, root: Path, manifest: AtlasManifest) -> None:
        unity = root / "unity2d" / "Assets" / "GameCreaterAtlas"
        unity.mkdir(parents=True, exist_ok=True)
        for page in manifest.pages:
            shutil.copy2(root / page.filename, unity / page.filename)
        (unity / "atlas.json").write_text(json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
        editor = unity / "Editor"
        editor.mkdir(parents=True, exist_ok=True)
        editor.joinpath("GameCreaterAtlasImporter.cs").write_text(
            r'''using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

[Serializable] public class GCAtlasPage { public int index; public string filename; public int width; public int height; }
[Serializable] public class GCAtlasSprite { public string asset_id; public string asset_name; public int page; public int x; public int y; public int width; public int height; }
[Serializable] public class GCAtlasDoc { public GCAtlasPage[] pages; public GCAtlasSprite[] sprites; }

public static class GameCreaterAtlasImporter {
  [MenuItem("Game Creater/Import Sprite Atlas")]
  public static void Import() {
    const string root = "Assets/GameCreaterAtlas";
    var doc = JsonUtility.FromJson<GCAtlasDoc>(File.ReadAllText(Path.Combine(root, "atlas.json")));
    foreach (var page in doc.pages) {
      var path = $"{root}/{page.filename}";
      var importer = AssetImporter.GetAtPath(path) as TextureImporter;
      if (importer == null) continue;
      importer.textureType = TextureImporterType.Sprite;
      importer.spriteImportMode = SpriteImportMode.Multiple;
      importer.alphaIsTransparency = true;
      importer.mipmapEnabled = false;
      var sprites = doc.sprites.Where(s => s.page == page.index).Select(s => new SpriteMetaData {
        name = s.asset_id,
        rect = new Rect(s.x, page.height - s.y - s.height, s.width, s.height),
        alignment = (int)SpriteAlignment.Center,
        pivot = new Vector2(.5f,.5f)
      }).ToArray();
      importer.spritesheet = sprites;
      importer.SaveAndReimport();
    }
    AssetDatabase.Refresh();
  }
}
''',
            encoding="utf-8",
        )

    @staticmethod
    def _next_power_of_two(value: int) -> int:
        value = max(1, int(value))
        return 1 << (value - 1).bit_length()

    @staticmethod
    def _is_power_of_two(value: int) -> bool:
        return value > 0 and value & (value - 1) == 0
