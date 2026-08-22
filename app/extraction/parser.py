from __future__ import annotations

import json

from app.extraction import ExtractionParseError, ParsedCandidate


def parse_response(text: str) -> list[ParsedCandidate]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExtractionParseError(f"Model response was not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ExtractionParseError("Top-level response must be a JSON object.")

    if "requirements" not in data:
        raise ExtractionParseError("Response is missing the 'requirements' key.")

    requirements = data["requirements"]
    if not isinstance(requirements, list):
        raise ExtractionParseError("'requirements' must be a list.")

    candidates: list[ParsedCandidate] = []
    for index, item in enumerate(requirements):
        if not isinstance(item, dict):
            raise ExtractionParseError(f"requirements[{index}] is not an object.")

        requirement_text = item.get("requirement_text")
        source_quote = item.get("source_quote")

        if not isinstance(requirement_text, str) or not requirement_text.strip():
            raise ExtractionParseError(
                f"requirements[{index}].requirement_text is missing, not a "
                f"string, or empty."
            )
        if not isinstance(source_quote, str) or not source_quote.strip():
            raise ExtractionParseError(
                f"requirements[{index}].source_quote is missing, not a "
                f"string, or empty."
            )

        candidates.append(
            ParsedCandidate(
                requirement_text=requirement_text.strip(),
                source_quote=source_quote,
            )
        )

    return candidates
