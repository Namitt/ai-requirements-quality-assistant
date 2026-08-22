from __future__ import annotations

from typing import Optional

from app.rules import RuleOutcome, SiblingText
from app.rules._text import similarity

WARN_THRESHOLD = 0.70
FAIL_THRESHOLD = 0.90


def _severity_for_score(score: float) -> Optional[str]:
    if score >= FAIL_THRESHOLD:
        return "fail"
    if score >= WARN_THRESHOLD:
        return "warn"
    return None


def evaluate(text: str, siblings: list[SiblingText]) -> RuleOutcome:
    candidates: list[tuple[SiblingText, float, str]] = []
    closest_miss: Optional[tuple[SiblingText, float]] = None

    for sibling in siblings:
        score = similarity(text, sibling.text)
        severity = _severity_for_score(score)
        if severity is not None:
            candidates.append((sibling, score, severity))
        elif closest_miss is None or score > closest_miss[1]:
            closest_miss = (sibling, score)

    if not candidates:
        if closest_miss is not None:
            sibling, score = closest_miss
            message = (
                f"No near-duplicate found. Closest match: requirement "
                f"#{sibling.id} at similarity {score:.2f}."
            )
        else:
            message = "No other requirements in the comparison scope."
        return RuleOutcome(result="pass", message=message, recommended_action=None)

    best_sibling, best_score, best_severity = max(
        candidates,
        key=lambda c: (1 if c[2] == "fail" else 0, c[1], -c[0].id),
    )

    if best_severity == "fail":
        return RuleOutcome(
            result="fail",
            message=(
                f"Near-exact duplicate of requirement #{best_sibling.id} "
                f"(similarity {best_score:.2f})."
            ),
            recommended_action=(
                "Decide which requirement is canonical and reject or merge "
                "the other."
            ),
        )

    return RuleOutcome(
        result="warn",
        message=(
            f"Possible duplicate of requirement #{best_sibling.id} "
            f"(similarity {best_score:.2f})."
        ),
        recommended_action=(
            "Confirm whether the two requirements are duplicates or "
            "legitimately distinct."
        ),
    )
