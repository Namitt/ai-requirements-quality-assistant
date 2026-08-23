from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.extraction import ExtractionAPIError
from app.extraction.client import AnthropicExtractionClient

# ---------------------------------------------------------------------------
# missing API key
# ---------------------------------------------------------------------------


def test_missing_api_key_raises_extraction_api_error_on_complete(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = AnthropicExtractionClient()

    with pytest.raises(ExtractionAPIError, match="ANTHROPIC_API_KEY"):
        client.complete("some prompt")


def test_empty_string_api_key_env_var_is_treated_as_missing(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    client = AnthropicExtractionClient()

    with pytest.raises(ExtractionAPIError, match="ANTHROPIC_API_KEY"):
        client.complete("some prompt")


def test_missing_api_key_error_does_not_expose_sdk_internals(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = AnthropicExtractionClient()

    with pytest.raises(ExtractionAPIError) as excinfo:
        client.complete("some prompt")

    message = str(excinfo.value)
    assert "traceback" not in message.lower()
    assert "_validate_headers" not in message
    assert "Could not resolve authentication method" not in message


def test_missing_api_key_does_not_fail_at_construction(monkeypatch):
    # Construction (e.g. via FastAPI's get_extraction_client dependency)
    # must not fail on a missing key - only actually trying to call the
    # model should, so that requests which never reach complete() (an
    # invalid request body, for example) are unaffected.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    client = AnthropicExtractionClient()

    assert client.model_name


# ---------------------------------------------------------------------------
# valid API key path - reaches the SDK call, without making a real one
# ---------------------------------------------------------------------------


def test_explicit_api_key_constructs_successfully(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    client = AnthropicExtractionClient(api_key="test-key-not-real")

    assert client.model_name
    assert client._client is not None


def test_api_key_from_environment_variable_is_used(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-from-env")

    client = AnthropicExtractionClient()

    assert client._client is not None


def test_configured_key_reaches_the_extraction_call_path(monkeypatch):
    # Proves a configured key lets complete() reach and use the SDK call,
    # without making a real network call - the SDK call itself is faked.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    client = AnthropicExtractionClient()

    fake_response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="fake model output")],
        model_dump_json=lambda: '{"fake": "response"}',
    )
    client._client.messages.create = lambda **kwargs: fake_response

    result = client.complete("some prompt")

    assert result.text == "fake model output"
    assert result.raw_response == '{"fake": "response"}'
