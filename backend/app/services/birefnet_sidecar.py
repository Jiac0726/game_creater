from __future__ import annotations

import base64
import io
import json
import os
import urllib.error
import urllib.request
from typing import Any

from PIL import Image


class BiRefNetSidecarError(RuntimeError):
    pass


class BiRefNetSidecarClient:
    """Stdlib HTTP client for the isolated localhost BiRefNet worker.

    Image bytes are exchanged in-memory as base64 PNG. The worker never receives
    filesystem paths, so it cannot read or write arbitrary files from the main
    backend environment.
    """

    def __init__(self) -> None:
        self.base_url = os.getenv("BIREFNET_SIDECAR_URL", "http://127.0.0.1:8010").rstrip("/")
        self.timeout = float(os.getenv("BIREFNET_SIDECAR_TIMEOUT", "120"))

    def health(self) -> dict[str, Any]:
        request = urllib.request.Request(f"{self.base_url}/health", method="GET")
        try:
            with urllib.request.urlopen(request, timeout=min(self.timeout, 10.0)) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            return {"ready": False, "error": str(exc), "url": self.base_url}

    def predict_alpha(self, image: Image.Image) -> Image.Image:
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="PNG")
        payload = json.dumps(
            {"image_base64": base64.b64encode(buffer.getvalue()).decode("ascii")}
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/predict",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise BiRefNetSidecarError(f"BiRefNet sidecar HTTP {exc.code}: {detail}") from exc
        except Exception as exc:
            raise BiRefNetSidecarError(f"BiRefNet sidecar unavailable: {exc}") from exc

        if not result.get("ok") or not result.get("alpha_base64"):
            raise BiRefNetSidecarError(result.get("error") or "BiRefNet sidecar prediction failed")
        try:
            alpha_bytes = base64.b64decode(result["alpha_base64"], validate=True)
            return Image.open(io.BytesIO(alpha_bytes)).convert("L")
        except Exception as exc:
            raise BiRefNetSidecarError(f"Invalid alpha response from BiRefNet sidecar: {exc}") from exc
