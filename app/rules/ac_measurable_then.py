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
# the start of a new structural Given/When/Then group. A capitalised
# "Given"/"When" only counts as a new group when it is structurally
# clause-initial - immediately after a comma, after sentence-ending
# punctuation, or at the very start of the text following "then" - not
# merely capitalised and present anywhere. This is what keeps an ordinary
# capitalised term inside the Then clause's own prose (e.g. "the Given Name
# field...") from being mistaken for a new scenario, while still catching a
# genuine second scenario whether it is introduced by "Given" or "When" and
# whether or not a full stop separates it from the first. Ordinary lowercase
# "given"/"when" inside the Then clause's own prose (e.g. "...shall be given
# a discount...", "...locked when 5 attempts occur...") are never scenario
# boundaries regardless of position, since only the capitalised form is
# checked at all. Sentence-ending punctuation excludes a decimal point (e.g.
# "2.5 seconds") via the lookaround assertions, so a measurable value
# straddling a "." is never split in half.
_SENTENCE_END_RE = re.compile(r"(?<!\d)[.!?](?!\d)")
_NEW_SCENARIO_RE = re.compile(r"(?:^|[,.!?])\s*(Given|When)\b")


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
    sentence_end = _SENTENCE_END_RE.search(remainder)
    new_scenario = _NEW_SCENARIO_RE.search(remainder)
    boundaries = [
        sentence_end.start() if sentence_end else None,
        new_scenario.start(1) if new_scenario else None,
    ]
    boundaries = [b for b in boundaries if b is not None]
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
