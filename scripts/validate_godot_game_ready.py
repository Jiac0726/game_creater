from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path


def run(command: list[str], *, cwd: Path | None = None) -> None:
    print("+", " ".join(command))
    completed = subprocess.run(command, cwd=cwd, text=True)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a Game Creater Godot 4 Game Ready Pack with a real Godot binary."
    )
    parser.add_argument("pack", type=Path, help="Game Ready ZIP exported for godot4")
    parser.add_argument(
        "--godot",
        default=os.environ.get("GODOT_BIN", "godot"),
        help="Godot executable (default: GODOT_BIN or godot)",
    )
    parser.add_argument("--keep", action="store_true", help="Keep the temporary project")
    args = parser.parse_args()

    if not args.pack.is_file():
        parser.error(f"pack not found: {args.pack}")
    godot = shutil.which(args.godot) if not Path(args.godot).is_file() else args.godot
    if not godot:
        parser.error(f"Godot executable not found: {args.godot}")

    temp_context = None
    if args.keep:
        root = Path(tempfile.mkdtemp(prefix="game_creater_godot_validate_"))
        print(f"Temporary project: {root}")
    else:
        temp_context = tempfile.TemporaryDirectory(prefix="game_creater_godot_validate_")
        root = Path(temp_context.name)

    try:
        with zipfile.ZipFile(args.pack) as archive:
            archive.extractall(root / "pack")

        pack_root = root / "pack"
        godot_source = pack_root / "godot4"
        if not godot_source.is_dir():
            raise SystemExit("ZIP does not contain a godot4/ package")
        shutil.copytree(godot_source, root / "godot4")
        (root / "project.godot").write_text(
            '[application]\nconfig/name="Game Creater Validation"\n\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n',
            encoding="utf-8",
        )

        resource_paths: list[str] = []
        for folder, suffixes in (("prefabs", {".tscn"}), ("animations", {".tscn"}), ("resources", {".tres"})):
            directory = root / "godot4" / folder
            if directory.is_dir():
                for path in sorted(directory.rglob("*")):
                    if path.suffix in suffixes:
                        resource_paths.append("res://" + path.relative_to(root).as_posix())

        validator = root / "validate_game_ready.gd"
        validator.write_text(
            "extends SceneTree\n\n"
            "func _initialize():\n"
            f"    var resources = {json.dumps(resource_paths)}\n"
            "    var failed = []\n"
            "    for path in resources:\n"
            "        var resource = load(path)\n"
            "        if resource == null:\n"
            "            failed.append(path)\n"
            "    if failed.size() > 0:\n"
            "        push_error(\"Game Creater validation failed: \" + str(failed))\n"
            "        quit(1)\n"
            "    print(\"Game Creater: loaded %d generated resources\" % resources.size())\n"
            "    quit(0)\n",
            encoding="utf-8",
        )

        run([str(godot), "--headless", "--path", str(root), "--import"])
        for script in sorted((root / "godot4" / "tilesets").glob("*.gd")):
            run(
                [
                    str(godot),
                    "--headless",
                    "--path",
                    str(root),
                    "--check-only",
                    "--script",
                    str(script),
                ]
            )
        run(
            [
                str(godot),
                "--headless",
                "--path",
                str(root),
                "--script",
                str(validator),
            ]
        )
        print("Godot Game Ready validation passed.")
        return 0
    finally:
        if temp_context is not None:
            temp_context.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
