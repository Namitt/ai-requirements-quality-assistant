from __future__ import annotations

import re
from typing import Optional

from app.rules import RuleOutcome, SiblingText
from app.rules._text import similarity
from app.rules.missing_acceptance_condition import NUMBER_UNIT_PATTERN

OVERLAP_THRESHOLD = 0.70
_NEGATION_RE = re.compile(r"\bshall not\b|\bnot\b", re.IGNORECASE)


def _first_number(text: str) -> Optional[float]:
    match = NUMBER_UNIT_PATTERN.search(text)
    if not match:
        return None
    return float(match.group(1))


def _has_negation(text: str) -> bool:
    return bool(_NEGATION_RE.search(text))


def evaluate(text: str, siblings: list[SiblingText]) -> RuleOutcome:
    candidates: list[tuple[SiblingText, float, str]] = []

    own_number = _first_number(text)
    own_negation = _has_negation(text)

    for sibling in siblings:
        score = similarity(text, sibling.text)
        if score < OVERLAP_THRESHOLD:
            continue

        reason = None
        sibling_number = _first_number(sibling.text)
        if (
            own_number is not None
            and sibling_number is not None
            and own_number != sibling_number
        ):
            reason = f"differing values ({own_number:g} vs {sibling_number:g})"
        elif own_negation != _has_negation(sibling.text):
            reason = "a negation present in one requirement but not the other"

        if reason is not None:
            candidates.append((sibling, score, reason))

    if not candidates:
        return RuleOutcome(
            result="pass",
            message="No possible contradiction found within the comparison scope.",
            recommended_action=None,
        )

    best_sibling, best_score, best_reason = max(candidates, key=lambda c: (c[1], -c[0].id))

    return RuleOutcome(
        result="warn",
        message=(
            f"Possible contradiction with requirement #{best_sibling.id} "
            f"({best_reason}) — requires human judgement, not a confirmed "
            f"contradiction."
        ),
        recommended_action=(
            "Manually compare the two flagged requirements; determine "
            "genuine contradiction vs. legitimately different scope; "
            "correct or annotate."
        ),
    )
