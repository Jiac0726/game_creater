from __future__ import annotations

import base64
import io
import json
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np
from PIL import Image


class CompletionError(RuntimeError):
    pass


def _data_uri_png(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


class CompletionProvider(ABC):
    name: str

    @abstractmethod
    def inpaint(
        self,
        image: Image.Image,
        mask: Image.Image,
        *,
        prompt: str,
        negative_prompt: str,
    ) -> Image.Image:
        raise NotImplementedError

    def health(self) -> dict:
        return {"ready": True, "provider": self.name}


class MockCompletionProvider(CompletionProvider):
    name = "mock"

    def inpaint(
        self,
        image: Image.Image,
        mask: Image.Image,
        *,
        prompt: str,
        negative_prompt: str,
    ) -> Image.Image:
        rgba = image.convert("RGBA")
        array = np.asarray(rgba).copy()
        mask_array = np.asarray(mask.convert("L"), dtype=np.uint8) > 127
        if mask_array.shape != array.shape[:2]:
            raise CompletionError("Completion mask size must match image size")
        array[mask_array, :3] = np.array([148, 126, 104], dtype=np.uint8)
        array[mask_array, 3] = 255
        return Image.fromarray(array, mode="RGBA")


class IOPaintCompletionProvider(CompletionProvider):
    name = "iopaint"

    def __init__(self) -> None:
        self.base_url = os.getenv("IOPAINT_URL", "http://127.0.0.1:8080").rstrip("/")
        self.timeout = float(os.getenv("GAME_CREATER_COMPLETION_TIMEOUT", "300"))

    def health(self) -> dict:
        request = urllib.request.Request(f"{self.base_url}/api/v1/model", method="GET")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                body = json.loads(response.read().decode("utf-8"))
            return {"ready": True, "provider": self.name, "model": body, "url": self.base_url}
        except Exception as exc:
            return {"ready": False, "provider": self.name, "error": str(exc), "url": self.base_url}

    def inpaint(
        self,
        image: Image.Image,
        mask: Image.Image,
        *,
        prompt: str,
        negative_prompt: str,
    ) -> Image.Image:
        image = image.convert("RGBA")
        mask = mask.convert("L")
        if image.size != mask.size:
            raise CompletionError("Completion mask size must match image size")

        payload = {
            "image": _data_uri_png(image),
            "mask": _data_uri_png(mask),
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "hd_strategy": "Crop",
            "hd_strategy_crop_trigger_size": 800,
            "hd_strategy_crop_margin": 128,
            "sd_keep_unmasked_area": True,
            "sd_seed": -1,
        }
        request = urllib.request.Request(
            f"{self.base_url}/api/v1/inpaint",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise CompletionError(f"IOPaint HTTP {exc.code}: {detail}") from exc
        except Exception as exc:
            raise CompletionError(f"IOPaint unavailable: {exc}") from exc

        try:
            return Image.open(io.BytesIO(data)).convert("RGBA")
        except Exception as exc:
            raise CompletionError("IOPaint response was not a valid image") from exc


class CompletionProviderRegistry:
    def __init__(self) -> None:
        self.providers: dict[str, CompletionProvider] = {
            "mock": MockCompletionProvider(),
            "iopaint": IOPaintCompletionProvider(),
        }

    def get(self, name: str) -> CompletionProvider:
        key = name.strip().lower()
        provider = self.providers.get(key)
        if provider is None:
            raise CompletionError(
                f"Unsupported completion provider {name!r}. Available: {', '.join(sorted(self.providers))}"
            )
        return provider

    def catalog(self) -> list[dict]:
        return [
            {"id": key, **provider.health()}
            for key, provider in self.providers.items()
        ]
