from __future__ import annotations

import json

from app.acceptance_criteria import AcceptanceCriteriaParseError, ParsedCriterion


def parse_response(text: str) -> ParsedCriterion:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AcceptanceCriteriaParseError(
            f"Model response was not valid JSON: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise AcceptanceCriteriaParseError("Top-level response must be a JSON object.")

    criterion_text = data.get("criterion_text")
    if not isinstance(criterion_text, str) or not criterion_text.strip():
        raise AcceptanceCriteriaParseError(
            "Response is missing a non-empty 'criterion_text' string."
        )

    return ParsedCriterion(criterion_text=criterion_text.strip())
