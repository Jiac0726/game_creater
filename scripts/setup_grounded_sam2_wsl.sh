#!/usr/bin/env bash
set -euo pipefail

MODELS_ROOT="${GAME_CREATER_MODELS_ROOT:-$HOME/.local/share/game_creater}"
GSAM_ROOT="$MODELS_ROOT/Grounded-SAM-2"

mkdir -p "$MODELS_ROOT"

if ! command -v git >/dev/null 2>&1; then
  echo "git is required." >&2
  exit 1
fi

if ! python - <<'PY'
try:
    import torch
    import torchvision
    print(f"torch={torch.__version__}, torchvision={torchvision.__version__}, cuda={torch.cuda.is_available()}")
except Exception as exc:
    raise SystemExit(f"PyTorch/TorchVision are not ready: {exc}")
PY
then
  cat >&2 <<'EOF'
Install a CUDA-compatible PyTorch + TorchVision build first, then re-run this script.
Use the official PyTorch selector so the CUDA runtime matches your machine.
EOF
  exit 1
fi

if [ ! -d "$GSAM_ROOT/.git" ]; then
  git clone https://github.com/IDEA-Research/Grounded-SAM-2.git "$GSAM_ROOT"
else
  git -C "$GSAM_ROOT" pull --ff-only
fi

python -m pip install -e "$GSAM_ROOT"
python -m pip install --no-build-isolation -e "$GSAM_ROOT/grounding_dino"

(
  cd "$GSAM_ROOT/checkpoints"
  bash download_ckpts.sh
)

(
  cd "$GSAM_ROOT/gdino_checkpoints"
  bash download_ckpts.sh
)

cat <<EOF

Grounded-SAM2 installation finished.

Export these variables before starting Game Creater:

export GAME_CREATER_MODE=grounded_sam2_local
export GAME_CREATER_DEVICE=auto
export GROUNDING_DINO_CONFIG="$GSAM_ROOT/grounding_dino/groundingdino/config/GroundingDINO_SwinT_OGC.py"
export GROUNDING_DINO_CHECKPOINT="$GSAM_ROOT/gdino_checkpoints/groundingdino_swint_ogc.pth"
export SAM2_MODEL_CONFIG="configs/sam2.1/sam2.1_hiera_l.yaml"
export SAM2_CHECKPOINT="$GSAM_ROOT/checkpoints/sam2.1_hiera_large.pt"

Then run:
  cd backend
  uvicorn app.main:app --host 0.0.0.0 --port 8000

Check:
  http://127.0.0.1:8000/api/v1/models/status
EOF
