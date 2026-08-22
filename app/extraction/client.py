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
        self._client = anthropic.Anthropic(api_key=api_key)
        self._anthropic = anthropic

    def complete(self, prompt: str) -> ExtractionCallResult:
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
