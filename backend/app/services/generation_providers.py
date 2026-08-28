from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from app.workflow_models import GenerationResult, GenerationSpec


class ImageGenerationError(RuntimeError):
    pass


class ImageGenerationProvider(ABC):
    name: str

    @abstractmethod
    def generate(self, spec: GenerationSpec, output_path: Path) -> GenerationResult:
        raise NotImplementedError


class MockImageGenerationProvider(ImageGenerationProvider):
    name = "mock"

    def generate(self, spec: GenerationSpec, output_path: Path) -> GenerationResult:
        width, height = self._parse_size(spec.size)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", (width, height), "#d7d0c5")
        draw = ImageDraw.Draw(image)

        # Deterministic visual placeholders: enough to validate generation -> split
        # workflow without an external model or network dependency.
        draw.rectangle((0, int(height * 0.62), width, height), fill="#7f796c")
        draw.rectangle(
            (int(width * 0.08), int(height * 0.22), int(width * 0.34), int(height * 0.70)),
            fill="#67584e",
        )
        draw.rectangle(
            (int(width * 0.47), int(height * 0.38), int(width * 0.65), int(height * 0.70)),
            fill="#9a6a46",
        )
        draw.ellipse(
            (int(width * 0.72), int(height * 0.28), int(width * 0.91), int(height * 0.70)),
            fill="#566b50",
        )
        image.save(output_path, format="PNG")

        return GenerationResult(
            provider=self.name,
            model="mock-generator-v1",
            image_file=str(output_path),
            prompt=spec.prompt,
            size=spec.size,
            quality=spec.quality,
            metadata={"offline": True, "negative_prompt": spec.negative_prompt},
        )

    @staticmethod
    def _parse_size(value: str) -> tuple[int, int]:
        try:
            width_text, height_text = value.lower().split("x", 1)
            width = int(width_text)
            height = int(height_text)
            if width <= 0 or height <= 0:
                raise ValueError
            return width, height
        except Exception:
            return 1024, 1024


class OpenAIImageGenerationProvider(ImageGenerationProvider):
    name = "openai"

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.timeout = float(os.getenv("GAME_CREATER_GENERATION_TIMEOUT", "300"))
        self.default_model = os.getenv("GAME_CREATER_OPENAI_IMAGE_MODEL", "gpt-image-2")

    def generate(self, spec: GenerationSpec, output_path: Path) -> GenerationResult:
        if not self.api_key:
            raise ImageGenerationError("OPENAI_API_KEY is not configured")

        model = (spec.model or self.default_model).strip()
        prompt = spec.prompt
        if spec.negative_prompt:
            prompt += f"\n\nAvoid: {spec.negative_prompt}."

        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "size": spec.size or "auto",
            "quality": spec.quality or "auto",
        }
        request = urllib.request.Request(
            f"{self.base_url}/images/generations",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ImageGenerationError(f"OpenAI image generation HTTP {exc.code}: {detail}") from exc
        except Exception as exc:
            raise ImageGenerationError(f"OpenAI image generation failed: {exc}") from exc

        try:
            item = body["data"][0]
            image_base64 = item["b64_json"]
            image_bytes = base64.b64decode(image_base64)
        except Exception as exc:
            raise ImageGenerationError("OpenAI image response did not contain data[0].b64_json") from exc

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(image_bytes)

        metadata: dict[str, Any] = {
            "negative_prompt": spec.negative_prompt,
        }
        if isinstance(body.get("usage"), dict):
            metadata["usage"] = body["usage"]
        if isinstance(item, dict) and item.get("revised_prompt"):
            metadata["revised_prompt"] = item["revised_prompt"]

        return GenerationResult(
            provider=self.name,
            model=model,
            image_file=str(output_path),
            prompt=spec.prompt,
            size=spec.size,
            quality=spec.quality,
            metadata=metadata,
        )


class ImageGenerationProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ImageGenerationProvider] = {
            "mock": MockImageGenerationProvider(),
            "openai": OpenAIImageGenerationProvider(),
        }

    def get(self, name: str) -> ImageGenerationProvider:
        key = name.strip().lower()
        provider = self._providers.get(key)
        if provider is None:
            raise ImageGenerationError(
                f"Unsupported generation provider {name!r}. Available: {', '.join(sorted(self._providers))}"
            )
        return provider

    def catalog(self) -> list[dict[str, Any]]:
        openai_provider = self._providers["openai"]
        assert isinstance(openai_provider, OpenAIImageGenerationProvider)
        return [
            {"id": "mock", "ready": True, "offline": True, "model": "mock-generator-v1"},
            {
                "id": "openai",
                "ready": bool(openai_provider.api_key),
                "offline": False,
                "model": openai_provider.default_model,
            },
        ]
