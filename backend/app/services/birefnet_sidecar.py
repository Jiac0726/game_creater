from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class BiRefNetSidecarError(RuntimeError):
    pass


class BiRefNetSidecarClient:
    """Small stdlib-only client for the isolated local BiRefNet worker.

    BiRefNet intentionally lives in another Python environment because its
    official dependency set currently conflicts with the main backend's NumPy
    version. The sidecar binds to localhost and exchanges only local file paths.
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

    def predict_alpha(self, image_path: str | Path, output_path: str | Path) -> dict[str, Any]:
        payload = json.dumps(
            {
                "image_path": str(Path(image_path).resolve()),
                "output_path": str(Path(output_path).resolve()),
            }
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

        if not result.get("ok"):
            raise BiRefNetSidecarError(result.get("error") or "BiRefNet sidecar prediction failed")
        return result
