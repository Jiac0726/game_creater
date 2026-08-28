#!/usr/bin/env bash
set -euo pipefail

ROOT="${GAME_CREATER_IOPAINT_ROOT:-$HOME/.local/share/game_creater/iopaint}"
VENV="$ROOT/.venv"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/game_creater"
ENV_FILE="$CONFIG_DIR/iopaint.env"
PYTHON_BIN="${PYTHON_BIN:-python3}"

mkdir -p "$ROOT" "$CONFIG_DIR"

"$PYTHON_BIN" -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip wheel setuptools
"$VENV/bin/python" -m pip install "iopaint==1.6.0"

cat > "$ENV_FILE" <<EOF
IOPAINT_URL=http://127.0.0.1:8080
IOPAINT_ROOT=$ROOT
IOPAINT_DEVICE=cpu
IOPAINT_MODEL=lama
IOPAINT_PORT=8080
EOF

cat <<EOF
IOPaint sidecar environment installed.

Config: $ENV_FILE

Start it with:
  bash scripts/start_iopaint_sidecar.sh

The first LaMa start may download model weights.
The original Sanster/IOPaint repository is archived; Game Creater talks to it only through a replaceable localhost API adapter.
EOF
