from __future__ import annotations

import re

from app.rules import RuleOutcome

NUMBER_UNIT_PATTERN = re.compile(r"\b(\d+(?:\.\d+)?)\s*[a-zA-Z%]+")
_THRESHOLD_PHRASE_RE = re.compile(
    r"\bat least\b|\bno more than\b|\bwithin\b", re.IGNORECASE
)
_CONDITIONAL_RE = re.compile(r"\bif\b|\bwhen\b|\bunless\b|\buntil\b", re.IGNORECASE)


def evaluate(text: str) -> RuleOutcome:
    has_signal = bool(
        NUMBER_UNIT_PATTERN.search(text)
        or _THRESHOLD_PHRASE_RE.search(text)
        or _CONDITIONAL_RE.search(text)
    )

    if has_signal:
        return RuleOutcome(
            result="pass",
            message="A measurable or testable acceptance condition was found.",
            recommended_action=None,
        )

    return RuleOutcome(
        result="warn",
        message="No measurable or testable acceptance condition was found.",
        recommended_action=(
            "Add a measurable condition if this requirement is meant to be "
            "delivery-ready, or approve as-is if it is intentionally a "
            "high-level statement awaiting decomposition."
        ),
    )
