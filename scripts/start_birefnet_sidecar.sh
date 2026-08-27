#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="${BIREFNET_ENV_FILE:-$HOME/.config/game_creater/birefnet.env}"

if [ ! -f "$ENV_FILE" ]; then
  echo "BiRefNet environment file not found: $ENV_FILE" >&2
  echo "Run: bash scripts/setup_birefnet_sidecar.sh" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

PY="${BIREFNET_VENV_DIR:-$HOME/.local/share/game_creater/birefnet-venv}/bin/python"
if [ ! -x "$PY" ]; then
  echo "BiRefNet Python not found: $PY" >&2
  exit 1
fi

HOST="${BIREFNET_SIDECAR_HOST:-127.0.0.1}"
PORT="${BIREFNET_SIDECAR_PORT:-8010}"
cd "$REPO_ROOT"
exec "$PY" -m uvicorn birefnet_worker.server:app --host "$HOST" --port "$PORT"
