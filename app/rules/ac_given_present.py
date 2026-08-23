from __future__ import annotations

import re

from app.rules import RuleOutcome

_GIVEN_RE = re.compile(r"\bgiven\b", re.IGNORECASE)


def evaluate(text: str) -> RuleOutcome:
    if _GIVEN_RE.search(text):
        return RuleOutcome(
            result="pass",
            message="A Given clause was found.",
            recommended_action=None,
        )

    return RuleOutcome(
        result="warn",
        message="No Given clause was found.",
        recommended_action=(
            "Add a Given clause describing the starting context, or confirm "
            "the criterion is intentionally structured differently."
        ),
    )
