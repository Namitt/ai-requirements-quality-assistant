from __future__ import annotations

import re

from app.rules import RuleOutcome
from app.rules.missing_acceptance_condition import (
    NUMBER_UNIT_PATTERN,
    _CONDITIONAL_RE,
    _THRESHOLD_PHRASE_RE,
)

_THEN_RE = re.compile(r"\bthen\b", re.IGNORECASE)


def evaluate(text: str) -> RuleOutcome:
    match = _THEN_RE.search(text)
    if match is None:
        return RuleOutcome(
            result="warn",
            message=(
                "No Then clause was found, so no measurable condition could "
                "be checked."
            ),
            recommended_action=(
                "Add a Then clause describing the expected, verifiable outcome."
            ),
        )

    then_segment = text[match.end() :]
    has_signal = bool(
        NUMBER_UNIT_PATTERN.search(then_segment)
        or _THRESHOLD_PHRASE_RE.search(then_segment)
        or _CONDITIONAL_RE.search(then_segment)
    )

    if has_signal:
        return RuleOutcome(
            result="pass",
            message="A measurable or testable condition was found in the Then clause.",
            recommended_action=None,
        )

    return RuleOutcome(
        result="warn",
        message="No measurable or testable condition was found in the Then clause.",
        recommended_action=(
            "Add a measurable condition (a number, threshold phrase, or "
            "conditional connector) to the Then clause."
        ),
    )
