from __future__ import annotations

import re

from app.rules import RuleOutcome

AMBIGUOUS_TERMS = (
    "user-friendly",
    "fast",
    "appropriate",
    "as needed",
    "TBD",
    "reasonable",
    "intuitive",
    "robust",
    "flexible",
    "easy to use",
    "adequate",
)

_TERM_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(term) for term in AMBIGUOUS_TERMS) + r")\b",
    re.IGNORECASE,
)


def evaluate(text: str) -> RuleOutcome:
    matches = sorted({m.group(0).lower() for m in _TERM_PATTERN.finditer(text)})

    if not matches:
        return RuleOutcome(
            result="pass",
            message="No ambiguous terms found.",
            recommended_action=None,
        )

    return RuleOutcome(
        result="warn",
        message=f"Ambiguous term(s) found: {', '.join(matches)}.",
        recommended_action=(
            "Rewrite with a measurable criterion if genuinely vague; "
            "otherwise dismiss with acknowledgement."
        ),
    )
