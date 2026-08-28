from __future__ import annotations

import json
import re
import shutil
import zipfile
from pathlib import Path
from uuid import uuid4

from app.advanced_animation_models import (
    AdvancedAnimationExportRequest,
    AdvancedAnimationExportResult,
    AnimationEvent,
    AnimationEventCreate,
    AnimationStateSet,
    AnimationStateSetCreate,
    AnimationStateSetPatch,
    AnimationTransition,
    FrameBox,
    FrameBoxCreate,
    FrameBoxType,
)
from app.services.asset_2d_resources import Asset2DResourceService
from app.services.asset_library import utc_now


class AnimationStateSetNotFoundError(KeyError):
    pass


class AdvancedAnimationService:
    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace)
        self.resources = Asset2DResourceService(self.workspace)
        self.library = self.resources.library
        self.state_root = self.workspace.parent / ".game_creater_state" / "advanced_animation_exports"
        self.state_root.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        with self.library._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS animation_state_sets (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    states_json TEXT NOT NULL,
                    default_state TEXT NOT NULL,
                    directions_json TEXT NOT NULL,
                    transitions_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS animation_frame_events (
                    id TEXT PRIMARY KEY,
                    clip_id TEXT NOT NULL,
                    frame_index INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_animation_events_clip ON animation_frame_events(clip_id, frame_index);
                CREATE TABLE IF NOT EXISTS animation_frame_boxes (
                    id TEXT PRIMARY KEY,
                    clip_id TEXT NOT NULL,
                    frame_index INTEGER NOT NULL,
                    box_type TEXT NOT NULL,
                    x REAL NOT NULL,
                    y REAL NOT NULL,
                    width REAL NOT NULL,
                    height REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_animation_boxes_clip ON animation_frame_boxes(clip_id, frame_index);
                """
            )

    def create_state_set(self, request: AnimationStateSetCreate) -> AnimationStateSet:
        name = request.name.strip()
        if not name:
            raise ValueError("State set name cannot be empty")
        self._validate_state_data(request.states, request.default_state, request.directions, request.transitions)
        state_set_id = f"animset_{uuid4().hex[:12]}"
        now = utc_now()
        with self.library._connect() as db:
            db.execute(
                "INSERT INTO animation_state_sets(id,name,states_json,default_state,directions_json,transitions_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (
                    state_set_id,
                    name,
                    json.dumps(request.states, ensure_ascii=False),
                    request.default_state,
                    json.dumps(request.directions, ensure_ascii=False),
                    json.dumps([item.model_dump() for item in request.transitions], ensure_ascii=False),
                    now,
                    now,
                ),
            )
        return self.get_state_set(state_set_id)

    def list_state_sets(self) -> list[AnimationStateSet]:
        with self.library._connect() as db:
            rows = db.execute("SELECT * FROM animation_state_sets ORDER BY updated_at DESC, id").fetchall()
        return [self._hydrate_state_set(row) for row in rows]

    def get_state_set(self, state_set_id: str) -> AnimationStateSet:
        with self.library._connect() as db:
            row = db.execute("SELECT * FROM animation_state_sets WHERE id=?", (state_set_id,)).fetchone()
        if row is None:
            raise AnimationStateSetNotFoundError(state_set_id)
        return self._hydrate_state_set(row)

    def patch_state_set(self, state_set_id: str, patch: AnimationStateSetPatch) -> AnimationStateSet:
        current = self.get_state_set(state_set_id)
        data = current.model_dump()
        values = patch.model_dump(exclude_unset=True)
        data.update(values)
        states = data["states"]
        default_state = data["default_state"]
        directions = data["directions"]
        transitions = [item if isinstance(item, AnimationTransition) else AnimationTransition(**item) for item in data["transitions"]]
        self._validate_state_data(states, default_state, directions, transitions)
        name = str(data["name"]).strip()
        if not name:
            raise ValueError("State set name cannot be empty")
        with self.library._connect() as db:
            db.execute(
                "UPDATE animation_state_sets SET name=?,states_json=?,default_state=?,directions_json=?,transitions_json=?,updated_at=? WHERE id=?",
                (
                    name,
                    json.dumps(states, ensure_ascii=False),
                    default_state,
                    json.dumps(directions, ensure_ascii=False),
                    json.dumps([item.model_dump() for item in transitions], ensure_ascii=False),
                    utc_now(),
                    state_set_id,
                ),
            )
        return self.get_state_set(state_set_id)

    def add_event(self, request: AnimationEventCreate) -> AnimationEvent:
        clip = self.resources.get_animation(request.clip_id)
        self._validate_frame_index(request.frame_index, len(clip.frame_asset_ids))
        name = request.name.strip()
        if not name:
            raise ValueError("Event name cannot be empty")
        event_id = f"animevt_{uuid4().hex[:12]}"
        now = utc_now()
        with self.library._connect() as db:
            db.execute(
                "INSERT INTO animation_frame_events(id,clip_id,frame_index,name,payload_json,created_at) VALUES (?,?,?,?,?,?)",
                (event_id, request.clip_id, request.frame_index, name, json.dumps(request.payload, ensure_ascii=False), now),
            )
        return AnimationEvent(id=event_id, clip_id=request.clip_id, frame_index=request.frame_index, name=name, payload=request.payload, created_at=now)

    def list_events(self, clip_id: str) -> list[AnimationEvent]:
        self.resources.get_animation(clip_id)
        with self.library._connect() as db:
            rows = db.execute("SELECT * FROM animation_frame_events WHERE clip_id=? ORDER BY frame_index,id", (clip_id,)).fetchall()
        return [AnimationEvent(id=row["id"], clip_id=row["clip_id"], frame_index=row["frame_index"], name=row["name"], payload=json.loads(row["payload_json"] or "{}"), created_at=row["created_at"]) for row in rows]

    def delete_event(self, event_id: str) -> None:
        with self.library._connect() as db:
            cur = db.execute("DELETE FROM animation_frame_events WHERE id=?", (event_id,))
            if cur.rowcount == 0:
                raise FileNotFoundError(event_id)

    def add_frame_box(self, request: FrameBoxCreate) -> FrameBox:
        clip = self.resources.get_animation(request.clip_id)
        self._validate_frame_index(request.frame_index, len(clip.frame_asset_ids))
        if request.x + request.width > 1.000001 or request.y + request.height > 1.000001:
            raise ValueError("Frame box must stay inside normalized 0..1 frame bounds")
        box_id = f"anbox_{uuid4().hex[:12]}"
        now = utc_now()
        with self.library._connect() as db:
            db.execute(
                "INSERT INTO animation_frame_boxes(id,clip_id,frame_index,box_type,x,y,width,height,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (box_id, request.clip_id, request.frame_index, request.box_type.value, request.x, request.y, request.width, request.height, now),
            )
        return FrameBox(id=box_id, clip_id=request.clip_id, frame_index=request.frame_index, box_type=request.box_type, x=request.x, y=request.y, width=request.width, height=request.height, created_at=now)

    def list_frame_boxes(self, clip_id: str) -> list[FrameBox]:
        self.resources.get_animation(clip_id)
        with self.library._connect() as db:
            rows = db.execute("SELECT * FROM animation_frame_boxes WHERE clip_id=? ORDER BY frame_index,id", (clip_id,)).fetchall()
        return [FrameBox(id=row["id"], clip_id=row["clip_id"], frame_index=row["frame_index"], box_type=FrameBoxType(row["box_type"]), x=row["x"], y=row["y"], width=row["width"], height=row["height"], created_at=row["created_at"]) for row in rows]

    def delete_frame_box(self, box_id: str) -> None:
        with self.library._connect() as db:
            cur = db.execute("DELETE FROM animation_frame_boxes WHERE id=?", (box_id,))
            if cur.rowcount == 0:
                raise FileNotFoundError(box_id)

    def export(self, request: AdvancedAnimationExportRequest) -> AdvancedAnimationExportResult:
        state_sets = [self.get_state_set(item) for item in request.state_set_ids]
        clip_ids: list[str] = []
        for state_set in state_sets:
            clip_ids.extend(state_set.states.values())
            clip_ids.extend(state_set.directions.values())
        clip_ids = list(dict.fromkeys(clip_ids))
        clips = [self.resources.get_animation(item) for item in clip_ids]
        events = [event.model_dump(mode="json") for clip_id in clip_ids for event in self.list_events(clip_id)]
        boxes = [box.model_dump(mode="json") for clip_id in clip_ids for box in self.list_frame_boxes(clip_id)]
        export_id = f"advanim_{uuid4().hex[:12]}"
        root = self.state_root / export_id
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        doc = {
            "schema": "game-creater/advanced-animation/v1",
            "state_sets": [item.model_dump(mode="json") for item in state_sets],
            "clips": [item.model_dump(mode="json") for item in clips],
            "events": events,
            "frame_boxes": boxes,
        }
        (root / "advanced_animation.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        if request.engine == "godot4":
            self._write_godot(root, doc)
        elif request.engine == "unity2d":
            self._write_unity(root, doc)
        archive = self.state_root / f"{export_id}.zip"
        archive.unlink(missing_ok=True)
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    output.write(path, path.relative_to(root))
        return AdvancedAnimationExportResult(export_id=export_id, engine=request.engine, state_set_count=len(state_sets), archive_path=str(archive), download_url=f"/api/v1/library/advanced-animation/exports/{export_id}")

    def export_path(self, export_id: str) -> Path:
        if not re.fullmatch(r"advanim_[0-9a-f]{12}", export_id):
            raise ValueError("Invalid export id")
        path = self.state_root / f"{export_id}.zip"
        if not path.is_file():
            raise FileNotFoundError(path)
        return path

    def _validate_state_data(self, states: dict[str, str], default_state: str, directions: dict[str, str], transitions: list[AnimationTransition]) -> None:
        if not states:
            raise ValueError("At least one animation state is required")
        clean_states = {key.strip(): value.strip() for key, value in states.items() if key.strip() and value.strip()}
        if len(clean_states) != len(states):
            raise ValueError("State names and clip ids cannot be empty")
        if default_state not in states:
            raise ValueError("default_state must exist in states")
        for clip_id in list(states.values()) + list(directions.values()):
            self.resources.get_animation(clip_id)
        for transition in transitions:
            if transition.from_state not in states or transition.to_state not in states:
                raise ValueError("Transition states must exist in states")

    @staticmethod
    def _validate_frame_index(frame_index: int, frame_count: int) -> None:
        if frame_index < 0 or frame_index >= frame_count:
            raise ValueError(f"frame_index {frame_index} is outside clip frame range 0..{max(0, frame_count - 1)}")

    @staticmethod
    def _hydrate_state_set(row) -> AnimationStateSet:
        return AnimationStateSet(
            id=row["id"], name=row["name"], states=json.loads(row["states_json"]), default_state=row["default_state"],
            directions=json.loads(row["directions_json"] or "{}"),
            transitions=[AnimationTransition(**item) for item in json.loads(row["transitions_json"] or "[]")],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    @staticmethod
    def _write_godot(root: Path, doc: dict) -> None:
        folder = root / "godot4"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "advanced_animation.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        (folder / "GameCreaterAdvancedAnimation.gd").write_text(
            '''class_name GameCreaterAdvancedAnimation\nextends Node\n\nsignal frame_event(name: String, payload: Dictionary)\n\nvar state_set: Dictionary = {}\nvar current_state := ""\n\nfunc configure(data: Dictionary, set_id: String) -> void:\n    for item in data.get("state_sets", []):\n        if item.get("id") == set_id:\n            state_set = item\n            current_state = item.get("default_state", "")\n            return\n\nfunc clip_for_state(state: String, direction: String = "") -> String:\n    if direction != "" and state_set.get("directions", {}).has(direction):\n        return state_set["directions"][direction]\n    return state_set.get("states", {}).get(state, "")\n''',
            encoding="utf-8",
        )

    @staticmethod
    def _write_unity(root: Path, doc: dict) -> None:
        folder = root / "unity2d" / "Assets" / "GameCreaterAdvancedAnimation"
        editor = folder / "Editor"
        runtime = folder / "Runtime"
        editor.mkdir(parents=True, exist_ok=True)
        runtime.mkdir(parents=True, exist_ok=True)
        (folder / "advanced_animation.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        (runtime / "GameCreaterFrameBox.cs").write_text(
            'using UnityEngine;\npublic class GameCreaterFrameBox : MonoBehaviour { public string clipId; public int frameIndex; public string boxType; public Rect normalizedRect; }\n',
            encoding="utf-8",
        )
        (editor / "GameCreaterAdvancedAnimationBuilder.cs").write_text(
            r'''using System;
using System.IO;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;

[Serializable] public class GCTransition { public string from_state; public string to_state; public string trigger; }
[Serializable] public class GCStateSet { public string id; public string name; public string default_state; public SerializableDictionary states; public GCTransition[] transitions; }
[Serializable] public class GCEvent { public string clip_id; public int frame_index; public string name; }
[Serializable] public class GCDoc { public GCEvent[] events; }
[Serializable] public class SerializableDictionary { }

public static class GameCreaterAdvancedAnimationBuilder {
  [MenuItem("Game Creater/Build Advanced Animation Metadata")]
  public static void Build() {
    const string root = "Assets/GameCreaterAdvancedAnimation";
    if (!File.Exists(Path.Combine(root, "advanced_animation.json"))) throw new FileNotFoundException("advanced_animation.json");
    Debug.Log("Game Creater advanced animation metadata is ready. Animation clips are resolved from Assets/GameCreaterPack/Animations by clip id; state/event/hitbox data remains in advanced_animation.json for deterministic runtime import.");
    AssetDatabase.Refresh();
  }
}
''',
            encoding="utf-8",
        )
