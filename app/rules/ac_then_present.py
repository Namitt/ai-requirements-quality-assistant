from __future__ import annotations

import re

from app.rules import RuleOutcome

_THEN_RE = re.compile(r"\bthen\b", re.IGNORECASE)


def evaluate(text: str) -> RuleOutcome:
    if _THEN_RE.search(text):
        return RuleOutcome(
            result="pass",
            message="A Then clause was found.",
            recommended_action=None,
        )

    return RuleOutcome(
        result="warn",
        message="No Then clause was found.",
        recommended_action=(
            "Add a Then clause describing the expected, verifiable outcome."
        ),
    )
