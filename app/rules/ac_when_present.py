from __future__ import annotations

import re

from app.rules import RuleOutcome

_WHEN_RE = re.compile(r"\bwhen\b", re.IGNORECASE)


def evaluate(text: str) -> RuleOutcome:
    if _WHEN_RE.search(text):
        return RuleOutcome(
            result="pass",
            message="A When clause was found.",
            recommended_action=None,
        )

    return RuleOutcome(
        result="warn",
        message="No When clause was found.",
        recommended_action=(
            "Add a When clause describing the triggering action or event, or "
            "confirm the criterion is intentionally structured differently."
        ),
    )
