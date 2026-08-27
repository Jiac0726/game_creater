#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="${GAME_CREATER_ENV_FILE:-$HOME/.config/game_creater/grounded_sam2.env}"
BIREFNET_ENV_FILE="${BIREFNET_ENV_FILE:-$HOME/.config/game_creater/birefnet.env}"
HOST="${GAME_CREATER_HOST:-0.0.0.0}"
PORT="${GAME_CREATER_PORT:-8000}"
PYTHON_BIN="${PYTHON_BIN:-python}"

if [ ! -f "$ENV_FILE" ]; then
  echo "Environment file not found: $ENV_FILE" >&2
  echo "Run: bash scripts/setup_grounded_sam2_wsl.sh" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
if [ -f "$BIREFNET_ENV_FILE" ]; then
  # shellcheck disable=SC1090
  source "$BIREFNET_ENV_FILE"
  echo "BiRefNet sidecar integration enabled from: $BIREFNET_ENV_FILE"
fi
set +a

"$PYTHON_BIN" "$SCRIPT_DIR/verify_grounded_sam2_env.py" --env-file "$ENV_FILE"

cd "$REPO_ROOT/backend"
exec "$PYTHON_BIN" -m uvicorn app.main:app --host "$HOST" --port "$PORT"
