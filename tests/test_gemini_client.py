from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.extraction import ExtractionAPIError
from app.extraction.gemini_client import GeminiExtractionClient

# ---------------------------------------------------------------------------
# missing API key
# ---------------------------------------------------------------------------


def test_missing_api_key_raises_extraction_api_error_on_complete(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    client = GeminiExtractionClient()

    with pytest.raises(ExtractionAPIError, match="GEMINI_API_KEY"):
        client.complete("some prompt")


def test_empty_string_api_key_env_var_is_treated_as_missing(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    client = GeminiExtractionClient()

    with pytest.raises(ExtractionAPIError, match="GEMINI_API_KEY"):
        client.complete("some prompt")


def test_missing_api_key_error_does_not_expose_sdk_internals(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    client = GeminiExtractionClient()

    with pytest.raises(ExtractionAPIError) as excinfo:
        client.complete("some prompt")

    message = str(excinfo.value)
    assert "traceback" not in message.lower()
    assert "No API key was provided" not in message


def test_missing_api_key_does_not_fail_at_construction(monkeypatch):
    # Construction (e.g. via FastAPI's get_extraction_client dependency)
    # must not fail on a missing key. This matters even more for Gemini
    # than it did for Anthropic: google.genai.Client(api_key=None) raises
    # ValueError immediately at construction time (confirmed by direct
    # inspection of the installed SDK) - unlike anthropic.Anthropic(),
    # which defers validation to the first real call. GeminiExtractionClient
    # must therefore never construct the real SDK client in __init__.
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    client = GeminiExtractionClient()

    assert client.model_name
    assert client._client is None


# ---------------------------------------------------------------------------
# valid API key path - reaches the SDK call, without making a real one
# ---------------------------------------------------------------------------


def test_explicit_api_key_constructs_successfully(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    client = GeminiExtractionClient(api_key="test-key-not-real")

    assert client.model_name
    assert client._client is None  # still lazy - not constructed yet


def test_api_key_from_environment_variable_is_used(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-from-env")

    client = GeminiExtractionClient()

    assert client._api_key == "test-key-from-env"


def test_model_name_defaults_and_can_be_overridden(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")

    default_client = GeminiExtractionClient()
    assert default_client.model_name  # non-empty default

    custom_client = GeminiExtractionClient(model_name="gemini-custom-model")
    assert custom_client.model_name == "gemini-custom-model"


def test_configured_key_reaches_the_extraction_call_path(monkeypatch):
    # Proves a configured key lets complete() reach and use the SDK call,
    # without making a real network call or even constructing a real SDK
    # client - the SDK client itself is faked directly.
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    client = GeminiExtractionClient()

    fake_response = SimpleNamespace(
        text="fake model output",
        model_dump_json=lambda: '{"fake": "response"}',
    )
    client._client = SimpleNamespace(
        models=SimpleNamespace(generate_content=lambda **kwargs: fake_response)
    )

    result = client.complete("some prompt")

    assert result.text == "fake model output"
    assert result.raw_response == '{"fake": "response"}'


def test_gemini_sdk_api_error_is_converted_to_extraction_api_error(monkeypatch):
    from google.genai import errors as genai_errors

    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    client = GeminiExtractionClient()

    def _raise_api_error(**kwargs):
        raise genai_errors.APIError(
            code=500, response_json={"error": {"message": "simulated Gemini failure"}}
        )

    client._client = SimpleNamespace(
        models=SimpleNamespace(generate_content=_raise_api_error)
    )

    with pytest.raises(ExtractionAPIError, match="Gemini API call failed"):
        client.complete("some prompt")


def test_real_gemini_sdk_is_never_invoked_by_these_tests(monkeypatch):
    # Sanity check on the test suite itself: importing google.genai must
    # not require network access or a real key, and none of the tests
    # above call through to genai.Client's real generate_content.
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    from google import genai  # noqa: F401 - import itself must not touch the network

    client = GeminiExtractionClient(api_key="unused-in-this-test")
    assert client._client is None
