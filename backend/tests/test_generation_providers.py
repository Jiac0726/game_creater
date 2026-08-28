from __future__ import annotations

from PIL import Image

from app.services.generation_providers import ImageGenerationProviderRegistry
from app.workflow_models import GenerationSpec


def test_mock_generation_provider_writes_png(tmp_path) -> None:
    provider = ImageGenerationProviderRegistry().get("mock")
    output = tmp_path / "source.png"
    result = provider.generate(
        GenerationSpec(
            provider="mock",
            size="640x360",
            quality="medium",
            prompt="test scene",
        ),
        output,
    )

    assert result.provider == "mock"
    assert output.is_file()
    with Image.open(output) as image:
        assert image.size == (640, 360)


def test_provider_catalog_always_contains_mock(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    catalog = ImageGenerationProviderRegistry().catalog()
    by_id = {item["id"]: item for item in catalog}

    assert by_id["mock"]["ready"] is True
    assert by_id["openai"]["ready"] is False
