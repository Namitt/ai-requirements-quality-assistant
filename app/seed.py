from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import ValidationRule

VALIDATION_RULES = [
    {
        "code": "DUPLICATE_NEAR",
        "name": "Duplicate / near-duplicate",
        "description": (
            "Catch requirements that restate an existing one, creating "
            "redundant or conflicting requirements downstream."
        ),
        "default_severity": "fail",
    },
    {
        "code": "AMBIGUOUS_WORDING",
        "name": "Ambiguous wording",
        "description": "Flag subjective or untestable terms.",
        "default_severity": "warn",
    },
    {
        "code": "MISSING_ACCEPTANCE_CONDITION",
        "name": "Missing acceptance condition",
        "description": (
            "Flag requirements lacking a measurable or testable condition."
        ),
        "default_severity": "warn",
    },
    {
        "code": "MISSING_ACTOR",
        "name": "Missing actor",
        "description": (
            "Flag requirements with no clear subject performing the action."
        ),
        "default_severity": "warn",
    },
    {
        "code": "POSSIBLE_CONTRADICTION",
        "name": "Possible contradiction",
        "description": (
            "Surface requirement pairs that appear to set conflicting rules "
            "for the same subject. The highest-stakes issue in the set, and "
            "the least reliable to detect — must never be described as "
            '"contradiction detected," only as a possible contradiction '
            "requiring human judgement."
        ),
        "default_severity": "warn",
    },
]


def seed_validation_rules(session: Session) -> None:
    existing_codes = {code for (code,) in session.query(ValidationRule.code).all()}
    for rule in VALIDATION_RULES:
        if rule["code"] not in existing_codes:
            session.add(ValidationRule(**rule))
    session.commit()
