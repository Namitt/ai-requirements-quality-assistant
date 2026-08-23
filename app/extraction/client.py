from __future__ import annotations

import os
from typing import Protocol

from app.extraction import ExtractionAPIError, ExtractionCallResult

DEFAULT_MODEL_NAME = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
DEFAULT_MAX_TOKENS = 4096


class ExtractionClient(Protocol):
    model_name: str

    def complete(self, prompt: str) -> ExtractionCallResult: ...


class AnthropicExtractionClient:
    def __init__(
        self,
        model_name: str | None = None,
        api_key: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ):
        import anthropic

        self.model_name = model_name or DEFAULT_MODEL_NAME
        self.max_tokens = max_tokens
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._client = anthropic.Anthropic(api_key=self._api_key)
        self._anthropic = anthropic

    def complete(self, prompt: str) -> ExtractionCallResult:
        # The Anthropic SDK resolves api_key from ANTHROPIC_API_KEY when it
        # isn't passed explicitly, exactly like the check above does - but
        # it only validates that resolution lazily, inside messages.create(),
        # where it raises a bare TypeError rather than anthropic.APIError.
        # That TypeError is not a configuration failure this client already
        # knows how to report, so it would otherwise surface as a generic,
        # unhelpful 500. Checking explicitly here, immediately before the
        # only place the SDK actually needs the key, turns a missing key
        # into the same documented ExtractionAPIError -> 502 path already
        # used for every other "the AI service could not be used" case -
        # without making client construction itself (e.g. via FastAPI's
        # get_extraction_client dependency) fail for requests that would
        # never reach this call anyway, such as ones with an invalid body.
        if not self._api_key:
            raise ExtractionAPIError(
                "ANTHROPIC_API_KEY is not configured. Set the "
                "ANTHROPIC_API_KEY environment variable before running "
                "live extraction, or use replay mode instead."
            )

        try:
            response = self._client.messages.create(
                model=self.model_name,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except self._anthropic.APIError as exc:
            raise ExtractionAPIError(f"Anthropic API call failed: {exc}") from exc

        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        return ExtractionCallResult(text=text, raw_response=response.model_dump_json())
