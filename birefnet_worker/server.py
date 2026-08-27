from __future__ import annotations

import base64
import io
import os
from contextlib import nullcontext
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from PIL import Image

MODEL_ID = os.getenv("BIREFNET_MODEL_ID", "ZhengPeng7/BiRefNet_HR-matting").strip()
MODEL_REVISION = os.getenv("BIREFNET_MODEL_REVISION", "").strip() or None
REQUESTED_DEVICE = os.getenv("BIREFNET_DEVICE", "auto").strip().lower()
INPUT_SIZE = max(256, min(2304, int(os.getenv("BIREFNET_INPUT_SIZE", "1024"))))
LOCAL_FILES_ONLY = os.getenv("BIREFNET_LOCAL_FILES_ONLY", "1").strip() not in {"0", "false", "False"}
MAX_IMAGE_BYTES = max(1_000_000, int(os.getenv("BIREFNET_MAX_IMAGE_BYTES", str(20 * 1024 * 1024))))

app = FastAPI(title="Game Creater BiRefNet Sidecar", version="0.1.0")

_model: Any | None = None
_transform: Any | None = None
_torch: Any | None = None
_device: str | None = None


class PredictRequest(BaseModel):
    image_base64: str = Field(min_length=4)


def _ensure_loaded() -> None:
    global _model, _transform, _torch, _device
    if _model is not None:
        return

    import torch
    from torchvision import transforms
    from transformers import AutoModelForImageSegmentation

    if REQUESTED_DEVICE == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("BIREFNET_DEVICE=cuda requested but CUDA is unavailable")
        device = "cuda"
    elif REQUESTED_DEVICE == "cpu":
        device = "cpu"
    else:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    kwargs: dict[str, Any] = {
        "trust_remote_code": True,
        "local_files_only": LOCAL_FILES_ONLY,
    }
    if MODEL_REVISION:
        kwargs["revision"] = MODEL_REVISION

    model = AutoModelForImageSegmentation.from_pretrained(MODEL_ID, **kwargs)
    torch.set_float32_matmul_precision("high")
    model.to(device)
    model.eval()

    transform = transforms.Compose(
        [
            transforms.Resize((INPUT_SIZE, INPUT_SIZE)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]
    )

    _torch = torch
    _model = model
    _transform = transform
    _device = device


@app.get("/health")
def health() -> dict[str, Any]:
    cuda_available = None
    try:
        import torch

        cuda_available = bool(torch.cuda.is_available())
    except Exception:
        pass
    return {
        "ready": True,
        "loaded": _model is not None,
        "model_id": MODEL_ID,
        "revision": MODEL_REVISION,
        "device_requested": REQUESTED_DEVICE,
        "device": _device,
        "cuda_available": cuda_available,
        "input_size": INPUT_SIZE,
        "local_files_only": LOCAL_FILES_ONLY,
    }


@app.post("/predict")
def predict(request: PredictRequest) -> dict[str, Any]:
    try:
        image_bytes = base64.b64decode(request.image_base64, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="image_base64 is invalid") from exc
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Input image is too large")

    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        _ensure_loaded()
        assert _model is not None
        assert _transform is not None
        assert _torch is not None
        assert _device is not None

        tensor = _transform(image).unsqueeze(0).to(_device)
        autocast = (
            _torch.amp.autocast(device_type="cuda", dtype=_torch.float16)
            if _device == "cuda"
            else nullcontext()
        )
        with autocast, _torch.no_grad():
            prediction = _model(tensor)[-1].sigmoid().to(_torch.float32).cpu()[0].squeeze()

        alpha = Image.fromarray(
            (prediction.numpy().clip(0, 1) * 255).astype("uint8"),
            mode="L",
        ).resize(image.size, Image.Resampling.BILINEAR)
        buffer = io.BytesIO()
        alpha.save(buffer, format="PNG")
        return {
            "ok": True,
            "alpha_base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
            "width": image.width,
            "height": image.height,
            "model_id": MODEL_ID,
            "revision": MODEL_REVISION,
            "device": _device,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
