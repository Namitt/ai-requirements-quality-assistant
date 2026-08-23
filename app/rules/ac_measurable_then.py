from __future__ import annotations

import re

from app.rules import RuleOutcome
from app.rules.missing_acceptance_condition import (
    NUMBER_UNIT_PATTERN,
    _CONDITIONAL_RE,
    _THRESHOLD_PHRASE_RE,
)

_THEN_RE = re.compile(r"\bthen\b", re.IGNORECASE)

# The Then clause ends at whichever comes first: the end of its sentence, or
# the start of a new structural Given/When/Then group. Only a capitalised,
# sentence-initial "Given" is treated as a new group - ordinary lowercase
# "given"/"when" inside the Then clause's own prose (e.g. "...shall be given
# a discount...", "...locked when 5 attempts occur...") are not scenario
# boundaries and must stay inside the scanned segment. Sentence-ending
# punctuation excludes a decimal point (e.g. "2.5 seconds") via the
# lookaround assertions, so a measurable value straddling a "." is never
# split in half.
_SENTENCE_END_RE = re.compile(r"(?<!\d)[.!?](?!\d)")
_NEW_SCENARIO_RE = re.compile(r"\bGiven\b")


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

    remainder = text[match.end() :]
    boundaries = [
        m.start()
        for m in (_SENTENCE_END_RE.search(remainder), _NEW_SCENARIO_RE.search(remainder))
        if m is not None
    ]
    then_segment = remainder[: min(boundaries)] if boundaries else remainder
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
