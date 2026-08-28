from __future__ import annotations

import argparse
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
        description="Validate a Game Creater Unity 2D Game Ready Pack with a real Unity Editor."
    )
    parser.add_argument("pack", type=Path, help="Game Ready ZIP exported for unity2d")
    parser.add_argument(
        "--unity",
        default=os.environ.get("UNITY_BIN", "Unity"),
        help="Unity Editor executable (default: UNITY_BIN or Unity)",
    )
    parser.add_argument("--keep", action="store_true", help="Keep the temporary Unity project")
    args = parser.parse_args()

    if not args.pack.is_file():
        parser.error(f"pack not found: {args.pack}")
    unity = shutil.which(args.unity) if not Path(args.unity).is_file() else args.unity
    if not unity:
        parser.error(f"Unity executable not found: {args.unity}")

    temp_context = None
    if args.keep:
        root = Path(tempfile.mkdtemp(prefix="game_creater_unity_validate_"))
        print(f"Temporary project: {root}")
    else:
        temp_context = tempfile.TemporaryDirectory(prefix="game_creater_unity_validate_")
        root = Path(temp_context.name)

    try:
        extract_root = root / "pack"
        with zipfile.ZipFile(args.pack) as archive:
            archive.extractall(extract_root)
        source = extract_root / "unity2d" / "Assets" / "GameCreaterPack"
        if not source.is_dir():
            raise SystemExit("ZIP does not contain unity2d/Assets/GameCreaterPack")

        project = root / "UnityProject"
        run([str(unity), "-batchmode", "-quit", "-createProject", str(project), "-logFile", "-"])
        target = project / "Assets" / "GameCreaterPack"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)

        run(
            [
                str(unity),
                "-batchmode",
                "-quit",
                "-projectPath",
                str(project),
                "-executeMethod",
                "GameCreaterGameReady2DBuilder.Build",
                "-logFile",
                "-",
            ]
        )

        required_dirs = [target / "Prefabs", target / "Animations", target / "Tiles"]
        missing = [str(path) for path in required_dirs if not path.exists()]
        if missing:
            raise SystemExit("Unity validation completed but generated resource folders are missing: " + ", ".join(missing))
        print("Unity Game Ready validation passed.")
        return 0
    finally:
        if temp_context is not None:
            temp_context.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
