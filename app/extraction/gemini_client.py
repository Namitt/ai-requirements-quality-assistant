from __future__ import annotations

import os

from app.extraction import ExtractionAPIError, ExtractionCallResult

DEFAULT_MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
DEFAULT_MAX_OUTPUT_TOKENS = 4096


class GeminiExtractionClient:
    """Implements the same ExtractionClient protocol as
    AnthropicExtractionClient (app/extraction/client.py) - model_name plus
    complete(prompt) -> ExtractionCallResult - so the rest of the
    application (engines, parsers, routes) never knows or needs to know
    which provider drafted the text.

    The Gemini SDK is imported only inside this module - nothing else in
    the application imports google.genai.
    """

    def __init__(
        self,
        model_name: str | None = None,
        api_key: str | None = None,
        max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    ):
        self.model_name = model_name or DEFAULT_MODEL_NAME
        self.max_output_tokens = max_output_tokens
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY")
        # Deliberately NOT constructing google.genai.Client here. Unlike
        # anthropic.Anthropic(), which resolves/validates its api_key
        # lazily (only inside the first real call), genai.Client(...)
        # validates eagerly at construction time and raises ValueError
        # immediately if no key is resolvable - confirmed by direct
        # inspection of the installed SDK, not assumed from the Anthropic
        # client's shape. Constructing it here would reintroduce exactly
        # the bug class this design exists to avoid: a missing key failing
        # as a side effect of FastAPI's get_extraction_client dependency
        # resolution, which pre-empts request body validation (see
        # AnthropicExtractionClient's own comment and
        # tests/test_api_extraction.py::test_missing_api_key_returns_502_with_actionable_message
        # for the historical regression this pattern fixes). The real SDK
        # client is built lazily, inside complete(), only after the
        # explicit key check below has already passed.
        self._client = None

    def complete(self, prompt: str) -> ExtractionCallResult:
        if not self._api_key:
            raise ExtractionAPIError(
                "GEMINI_API_KEY is not configured. Set the GEMINI_API_KEY "
                "environment variable before running live extraction, or "
                "use replay mode instead."
            )

        from google import genai
        from google.genai import errors as genai_errors

        if self._client is None:
            self._client = genai.Client(api_key=self._api_key)

        try:
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    max_output_tokens=self.max_output_tokens
                ),
            )
        except genai_errors.APIError as exc:
            raise ExtractionAPIError(f"Gemini API call failed: {exc}") from exc

        return ExtractionCallResult(
            text=response.text or "", raw_response=response.model_dump_json()
        )
