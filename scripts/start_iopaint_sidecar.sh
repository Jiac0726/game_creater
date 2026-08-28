#!/usr/bin/env bash
set -euo pipefail

CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/game_creater"
ENV_FILE="${GAME_CREATER_IOPAINT_ENV_FILE:-$CONFIG_DIR/iopaint.env}"

if [ ! -f "$ENV_FILE" ]; then
  echo "IOPaint env file not found: $ENV_FILE" >&2
  echo "Run: bash scripts/setup_iopaint_sidecar.sh" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

ROOT="${IOPAINT_ROOT:-$HOME/.local/share/game_creater/iopaint}"
VENV="$ROOT/.venv"
DEVICE="${IOPAINT_DEVICE:-cpu}"
MODEL="${IOPAINT_MODEL:-lama}"
PORT="${IOPAINT_PORT:-8080}"
MODEL_DIR="$ROOT/models"

if [ ! -x "$VENV/bin/iopaint" ]; then
  echo "IOPaint executable missing: $VENV/bin/iopaint" >&2
  exit 1
fi

mkdir -p "$MODEL_DIR"
exec "$VENV/bin/iopaint" start \
  --host=127.0.0.1 \
  --port="$PORT" \
  --device="$DEVICE" \
  --model="$MODEL" \
  --model-dir="$MODEL_DIR"
