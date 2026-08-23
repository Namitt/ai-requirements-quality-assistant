from __future__ import annotations

import pytest

from app.api.deps import get_extraction_client
from app.extraction import ExtractionAPIError
from app.extraction.client import AnthropicExtractionClient
from app.extraction.gemini_client import GeminiExtractionClient


def test_unset_ai_provider_defaults_to_anthropic(monkeypatch):
    monkeypatch.delenv("AI_PROVIDER", raising=False)

    client = get_extraction_client()

    assert isinstance(client, AnthropicExtractionClient)


def test_ai_provider_anthropic_selects_anthropic_client(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "anthropic")

    client = get_extraction_client()

    assert isinstance(client, AnthropicExtractionClient)


def test_ai_provider_gemini_selects_gemini_client(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")

    client = get_extraction_client()

    assert isinstance(client, GeminiExtractionClient)


def test_ai_provider_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "GEMINI")

    client = get_extraction_client()

    assert isinstance(client, GeminiExtractionClient)


def test_unsupported_ai_provider_raises_clear_configuration_error(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemin")  # deliberate typo

    with pytest.raises(ExtractionAPIError, match="gemin"):
        get_extraction_client()


def test_unsupported_ai_provider_does_not_silently_fall_back(monkeypatch):
    # An invalid value must never be quietly treated as anthropic (or any
    # other provider) - that would hide a real configuration mistake.
    monkeypatch.setenv("AI_PROVIDER", "openai")

    with pytest.raises(ExtractionAPIError):
        get_extraction_client()
