from __future__ import annotations

from typing import NamedTuple


class ExtractionError(RuntimeError):
    pass


class ExtractionAPIError(ExtractionError):
    pass


class ExtractionParseError(ExtractionError):
    pass


class SourceQuoteNotFoundError(ExtractionError):
    pass


class ExtractionCallResult(NamedTuple):
    text: str
    raw_response: str


class ParsedCandidate(NamedTuple):
    requirement_text: str
    source_quote: str
