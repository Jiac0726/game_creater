from __future__ import annotations

import json
import re
import shutil
import zipfile
from pathlib import Path
from uuid import uuid4

from app.advanced_tilemap_models import (
    TileCoordinate,
    TileMapCell,
    TileMapCreateRequest,
    TileMapEraseRequest,
    TileMapExportRequest,
    TileMapExportResult,
    TileMapLayer,
    TileMapLayerCreate,
    TileMapLayerType,
    TileMapPaintRequest,
    TileMapProject,
)
from app.asset_2d_models import AutoTileMode, TileSetDefinition
from app.services.asset_2d_resources import Asset2DResourceService
from app.services.asset_library import utc_now


class TileMapNotFoundError(KeyError):
    pass


class TileMapLayerNotFoundError(KeyError):
    pass


class AdvancedTileMapService:
    NEIGHBORS = [
        (0, -1, 1), (1, -1, 2), (1, 0, 4), (1, 1, 8),
        (0, 1, 16), (-1, 1, 32), (-1, 0, 64), (-1, -1, 128),
    ]

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace)
        self.resources = Asset2DResourceService(self.workspace)
        self.library = self.resources.library
        self.state_root = self.workspace.parent / ".game_creater_state" / "tilemap_exports"
        self.state_root.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        with self.library._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS game_tilemaps (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    tileset_id TEXT NOT NULL,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS game_tilemap_layers (
                    id TEXT PRIMARY KEY,
                    map_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    layer_type TEXT NOT NULL,
                    layer_order INTEGER NOT NULL,
                    visible INTEGER NOT NULL DEFAULT 1,
                    FOREIGN KEY(map_id) REFERENCES game_tilemaps(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS game_tilemap_cells (
                    layer_id TEXT NOT NULL,
                    x INTEGER NOT NULL,
                    y INTEGER NOT NULL,
                    asset_id TEXT,
                    terrain TEXT,
                    PRIMARY KEY(layer_id,x,y),
                    FOREIGN KEY(layer_id) REFERENCES game_tilemap_layers(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_tilemap_layers_map ON game_tilemap_layers(map_id,layer_order);
                CREATE INDEX IF NOT EXISTS idx_tilemap_cells_layer ON game_tilemap_cells(layer_id,x,y);
                """
            )

    def create(self, request: TileMapCreateRequest) -> TileMapProject:
        self.resources.get_tileset(request.tileset_id)
        name = request.name.strip()
        if not name:
            raise ValueError("TileMap name cannot be empty")
        map_id = f"tilemap_{uuid4().hex[:12]}"
        layer_id = f"tmlayer_{uuid4().hex[:12]}"
        now = utc_now()
        with self.library._connect() as db:
            db.execute("INSERT INTO game_tilemaps(id,name,tileset_id,width,height,created_at,updated_at) VALUES (?,?,?,?,?,?,?)", (map_id,name,request.tileset_id,request.width,request.height,now,now))
            db.execute("INSERT INTO game_tilemap_layers(id,map_id,name,layer_type,layer_order,visible) VALUES (?,?,?,?,0,1)", (layer_id,map_id,"Ground",TileMapLayerType.VISUAL.value))
        return self.get(map_id)

    def list(self) -> list[TileMapProject]:
        with self.library._connect() as db:
            rows = db.execute("SELECT id FROM game_tilemaps ORDER BY updated_at DESC,id").fetchall()
        return [self.get(row["id"]) for row in rows]

    def get(self, map_id: str) -> TileMapProject:
        with self.library._connect() as db:
            row = db.execute("SELECT * FROM game_tilemaps WHERE id=?", (map_id,)).fetchone()
            if row is None:
                raise TileMapNotFoundError(map_id)
            layers = db.execute("SELECT * FROM game_tilemap_layers WHERE map_id=? ORDER BY layer_order,id", (map_id,)).fetchall()
            result_layers=[]
            for layer in layers:
                cells=db.execute("SELECT * FROM game_tilemap_cells WHERE layer_id=? ORDER BY y,x", (layer["id"],)).fetchall()
                result_layers.append(TileMapLayer(id=layer["id"],name=layer["name"],layer_type=TileMapLayerType(layer["layer_type"]),order=layer["layer_order"],visible=bool(layer["visible"]),cells=[TileMapCell(x=c["x"],y=c["y"],asset_id=c["asset_id"],terrain=c["terrain"]) for c in cells]))
        return TileMapProject(id=row["id"],name=row["name"],tileset_id=row["tileset_id"],width=row["width"],height=row["height"],layers=result_layers,created_at=row["created_at"],updated_at=row["updated_at"])

    def add_layer(self, map_id: str, request: TileMapLayerCreate) -> TileMapProject:
        self.get(map_id)
        name=request.name.strip()
        if not name: raise ValueError("Layer name cannot be empty")
        layer_id=f"tmlayer_{uuid4().hex[:12]}"
        with self.library._connect() as db:
            order=db.execute("SELECT COALESCE(MAX(layer_order),-1)+1 AS n FROM game_tilemap_layers WHERE map_id=?",(map_id,)).fetchone()["n"]
            db.execute("INSERT INTO game_tilemap_layers(id,map_id,name,layer_type,layer_order,visible) VALUES (?,?,?,?,?,1)",(layer_id,map_id,name,request.layer_type.value,int(order)))
            db.execute("UPDATE game_tilemaps SET updated_at=? WHERE id=?",(utc_now(),map_id))
        return self.get(map_id)

    def paint(self, map_id: str, request: TileMapPaintRequest) -> TileMapProject:
        project=self.get(map_id)
        layer=self._require_layer(project,request.layer_id)
        tileset=self.resources.get_tileset(project.tileset_id)
        if request.asset_id is None and not (request.terrain or "").strip():
            raise ValueError("Paint requires asset_id or terrain")
        if request.asset_id is not None and request.asset_id not in tileset.tile_asset_ids:
            raise ValueError("asset_id is not part of this TileSet")
        terrain=(request.terrain or "").strip() or None
        if terrain and tileset.terrain_tags and terrain not in tileset.terrain_tags:
            raise ValueError("terrain is not declared by this TileSet")
        for cell in request.cells: self._validate_coord(project,cell)
        with self.library._connect() as db:
            for cell in request.cells:
                db.execute("INSERT INTO game_tilemap_cells(layer_id,x,y,asset_id,terrain) VALUES (?,?,?,?,?) ON CONFLICT(layer_id,x,y) DO UPDATE SET asset_id=excluded.asset_id,terrain=excluded.terrain",(layer.id,cell.x,cell.y,request.asset_id,terrain))
        if terrain and layer.layer_type==TileMapLayerType.VISUAL:
            self._recompute_terrain(project.id,layer.id,tileset,{(c.x,c.y) for c in request.cells})
        self._touch(map_id)
        return self.get(map_id)

    def erase(self, map_id: str, request: TileMapEraseRequest) -> TileMapProject:
        project=self.get(map_id); layer=self._require_layer(project,request.layer_id); tileset=self.resources.get_tileset(project.tileset_id)
        for cell in request.cells: self._validate_coord(project,cell)
        with self.library._connect() as db:
            for cell in request.cells: db.execute("DELETE FROM game_tilemap_cells WHERE layer_id=? AND x=? AND y=?",(layer.id,cell.x,cell.y))
        if layer.layer_type==TileMapLayerType.VISUAL:
            self._recompute_terrain(project.id,layer.id,tileset,{(c.x,c.y) for c in request.cells})
        self._touch(map_id); return self.get(map_id)

    def export(self,map_id:str,request:TileMapExportRequest)->TileMapExportResult:
        project=self.get(map_id); tileset=self.resources.get_tileset(project.tileset_id)
        export_id=f"tmexp_{uuid4().hex[:12]}"; root=self.state_root/export_id
        if root.exists(): shutil.rmtree(root)
        root.mkdir(parents=True)
        doc={"schema":"game-creater/tilemap/v1","map":project.model_dump(mode="json"),"tileset":tileset.model_dump(mode="json")}
        (root/"tilemap.json").write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding="utf-8")
        assets=root/"assets"; assets.mkdir()
        used=list(dict.fromkeys(c.asset_id for l in project.layers for c in l.cells if c.asset_id))
        for asset_id in used:
            asset=self.library.get(asset_id); src=self.workspace/asset.image_path
            if not src.is_file(): raise FileNotFoundError(src)
            shutil.copy2(src,assets/f"{asset_id}.png")
        if request.engine=="godot4": self._write_godot(root,project,tileset,used)
        elif request.engine=="unity2d": self._write_unity(root,project,tileset,used)
        archive=self.state_root/f"{export_id}.zip"; archive.unlink(missing_ok=True)
        with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED) as out:
            for path in sorted(root.rglob("*")):
                if path.is_file(): out.write(path,path.relative_to(root))
        return TileMapExportResult(export_id=export_id,map_id=map_id,engine=request.engine,archive_path=str(archive),download_url=f"/api/v1/library/tilemaps/exports/{export_id}")

    def export_path(self,export_id:str)->Path:
        if not re.fullmatch(r"tmexp_[0-9a-f]{12}",export_id): raise ValueError("Invalid export id")
        path=self.state_root/f"{export_id}.zip"
        if not path.is_file(): raise FileNotFoundError(path)
        return path

    def _recompute_terrain(self,map_id:str,layer_id:str,tileset:TileSetDefinition,changed:set[tuple[int,int]])->None:
        affected=set(changed)
        for x,y in list(changed):
            for dx,dy,_ in self.NEIGHBORS: affected.add((x+dx,y+dy))
        with self.library._connect() as db:
            rows=db.execute("SELECT x,y,terrain FROM game_tilemap_cells WHERE layer_id=?",(layer_id,)).fetchall()
            terrain_by={(r["x"],r["y"]):r["terrain"] for r in rows if r["terrain"]}
            for x,y in affected:
                terrain=terrain_by.get((x,y))
                if not terrain: continue
                mask=0
                for dx,dy,bit in self.NEIGHBORS:
                    if tileset.autotile_mode==AutoTileMode.CARDINAL4 and bit in {2,8,32,128}: continue
                    if terrain_by.get((x+dx,y+dy))==terrain: mask|=bit
                candidates=[r for r in tileset.terrain_rules if r.terrain==terrain]
                if candidates:
                    exact=[r for r in candidates if r.neighbor_mask==mask]
                    pool=exact or candidates
                    rule=max(pool,key=lambda r:((r.neighbor_mask & mask).bit_count(),r.priority))
                    asset_id=rule.asset_id
                else:
                    asset_id=tileset.tile_asset_ids[0] if tileset.tile_asset_ids else None
                db.execute("UPDATE game_tilemap_cells SET asset_id=? WHERE layer_id=? AND x=? AND y=?",(asset_id,layer_id,x,y))

    @staticmethod
    def _write_godot(root:Path,project:TileMapProject,tileset:TileSetDefinition,used:list[str])->None:
        godot=root/"godot4"; godot.mkdir()
        for aid in used: shutil.copy2(root/"assets"/f"{aid}.png",godot/f"{aid}.png")
        cells=[]
        for layer in project.layers:
            cells.append({"id":layer.id,"name":layer.name,"type":layer.layer_type.value,"order":layer.order,"cells":[c.model_dump() for c in layer.cells]})
        (godot/"tilemap_data.json").write_text(json.dumps({"map":project.model_dump(mode="json"),"tileset":tileset.model_dump(mode="json"),"layers":cells},ensure_ascii=False,indent=2),encoding="utf-8")
        paths=", ".join(f'"{aid}": "res://{aid}.png"' for aid in used)
        safe_name=AdvancedTileMapService._safe_name(project.name)
        script=f'''@tool\nextends EditorScript\n\nfunc _run():\n    var doc = JSON.parse_string(FileAccess.get_file_as_string("res://tilemap_data.json"))\n    var tile_set = TileSet.new()\n    tile_set.tile_size = Vector2i({tileset.tile_width}, {tileset.tile_height})\n    var texture_paths = {{{paths}}}\n    var source_ids = {{}}\n    var sid = 0\n    for asset_id in texture_paths.keys():\n        var tex = load(texture_paths[asset_id])\n        var source = TileSetAtlasSource.new()\n        source.texture = tex\n        source.texture_region_size = Vector2i({tileset.tile_width}, {tileset.tile_height})\n        source.create_tile(Vector2i(0,0))\n        tile_set.add_source(source, sid)\n        source_ids[asset_id] = sid\n        sid += 1\n    ResourceSaver.save(tile_set, "res://game_creater_tileset.tres")\n    var root = Node2D.new()\n    root.name = "{safe_name}"\n    for layer_doc in doc["layers"]:\n        var layer = TileMapLayer.new()\n        layer.name = layer_doc["name"]\n        layer.tile_set = tile_set\n        layer.z_index = int(layer_doc["order"])\n        for cell in layer_doc["cells"]:\n            var aid = cell.get("asset_id")\n            if aid != null and source_ids.has(aid):\n                layer.set_cell(Vector2i(int(cell["x"]), int(cell["y"])), source_ids[aid], Vector2i(0,0), 0)\n        root.add_child(layer)\n        layer.owner = root\n    var packed = PackedScene.new()\n    packed.pack(root)\n    ResourceSaver.save(packed, "res://{project.id}.tscn")\n'''
        (godot/"build_tilemap.gd").write_text(script,encoding="utf-8")
        (godot/"project.godot").write_text('[application]\nconfig/name="Game Creater TileMap"\n',encoding="utf-8")

    @staticmethod
    def _write_unity(root:Path,project:TileMapProject,tileset:TileSetDefinition,used:list[str])->None:
        base=root/"unity2d"/"Assets"/"GameCreaterTileMap"; editor=base/"Editor"; assets=base/"assets"; editor.mkdir(parents=True);assets.mkdir()
        for aid in used: shutil.copy2(root/"assets"/f"{aid}.png",assets/f"{aid}.png")
        (base/"tilemap.json").write_text((root/"tilemap.json").read_text(encoding="utf-8"),encoding="utf-8")
        editor.joinpath("GameCreaterTileMapBuilder.cs").write_text(r'''using System;\nusing System.IO;\nusing UnityEditor;\nusing UnityEditor.SceneManagement;\nusing UnityEngine;\nusing UnityEngine.Tilemaps;\n\n[Serializable] public class GCCell { public int x; public int y; public string asset_id; public string terrain; }\n[Serializable] public class GCLayer { public string id; public string name; public string layer_type; public int order; public bool visible; public GCCell[] cells; }\n[Serializable] public class GCMap { public string id; public string name; public int width; public int height; public GCLayer[] layers; }\n[Serializable] public class GCRoot { public GCMap map; }\n\npublic static class GameCreaterTileMapBuilder {\n [MenuItem("Game Creater/Build TileMap Scene")] public static void Build(){\n  const string root="Assets/GameCreaterTileMap"; var doc=JsonUtility.FromJson<GCRoot>(File.ReadAllText(Path.Combine(root,"tilemap.json")));\n  var scene=EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single); var grid=new GameObject("Grid",typeof(Grid));\n  foreach(var l in doc.map.layers){ var go=new GameObject(l.name,typeof(Tilemap),typeof(TilemapRenderer));go.transform.SetParent(grid.transform);go.SetActive(l.visible);var tm=go.GetComponent<Tilemap>();var renderer=go.GetComponent<TilemapRenderer>();renderer.sortingOrder=l.order;foreach(var c in l.cells){if(String.IsNullOrEmpty(c.asset_id))continue;var sprite=AssetDatabase.LoadAssetAtPath<Sprite>($"{root}/assets/{c.asset_id}.png");if(sprite==null)continue;var tile=ScriptableObject.CreateInstance<Tile>();tile.sprite=sprite;tm.SetTile(new Vector3Int(c.x,-c.y,0),tile);}}\n  Directory.CreateDirectory($"{root}/Scenes");EditorSceneManager.SaveScene(scene,$"{root}/Scenes/{doc.map.id}.unity");AssetDatabase.SaveAssets();AssetDatabase.Refresh();\n }\n}\n''',encoding="utf-8")

    def _require_layer(self,project:TileMapProject,layer_id:str)->TileMapLayer:
        for layer in project.layers:
            if layer.id==layer_id:return layer
        raise TileMapLayerNotFoundError(layer_id)

    @staticmethod
    def _validate_coord(project:TileMapProject,cell:TileCoordinate)->None:
        if cell.x<0 or cell.y<0 or cell.x>=project.width or cell.y>=project.height: raise ValueError("Tile coordinate outside map bounds")

    def _touch(self,map_id:str)->None:
        with self.library._connect() as db: db.execute("UPDATE game_tilemaps SET updated_at=? WHERE id=?",(utc_now(),map_id))

    @staticmethod
    def _safe_name(value:str)->str: return re.sub(r"[^A-Za-z0-9_]","_",value).strip("_") or "TileMap"