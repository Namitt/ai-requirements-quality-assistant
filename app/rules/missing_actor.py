from __future__ import annotations

import re

from app.rules import RuleOutcome

ACTOR_PHRASES = (
    "the system",
    "the user",
    "the users",
    "the administrator",
    "the administrators",
    "administrators",
    "the analyst",
    "the application",
    "the service",
)

_ACTOR_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(phrase) for phrase in ACTOR_PHRASES) + r")\b",
    re.IGNORECASE,
)


def evaluate(text: str) -> RuleOutcome:
    if _ACTOR_PATTERN.search(text):
        return RuleOutcome(
            result="pass",
            message="An actor was identified in the requirement text.",
            recommended_action=None,
        )

    return RuleOutcome(
        result="warn",
        message="No actor from the configured list was found in the requirement text.",
        recommended_action=(
            "Rewrite to name the responsible actor if clarity matters for "
            "delivery; approve if the actor is obvious from surrounding context."
        ),
    )
