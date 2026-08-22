from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ExtractedRequirement,
    ExtractionRun,
    Requirement,
    ValidationResult,
    ValidationRule,
    ValidationRun,
)
from app.rules import RuleOutcome, SiblingText
from app.rules import (
    ambiguous_wording,
    duplicate_near,
    missing_acceptance_condition,
    missing_actor,
    possible_contradiction,
)

VALIDATOR_VERSION = "1.0.0"

EXPECTED_RULE_CODES = (
    "DUPLICATE_NEAR",
    "AMBIGUOUS_WORDING",
    "MISSING_ACCEPTANCE_CONDITION",
    "MISSING_ACTOR",
    "POSSIBLE_CONTRADICTION",
)

_SEVERITY_ORDER = {"pass": 0, "warn": 1, "fail": 2}


class ValidationConfigurationError(RuntimeError):
    pass


def resolve_source_document_id(session: Session, requirement: Requirement) -> int | None:
    if requirement.source_extraction_id is None:
        return None
    extracted = session.get(ExtractedRequirement, requirement.source_extraction_id)
    extraction_run = session.get(ExtractionRun, extracted.extraction_run_id)
    return extraction_run.source_document_id


def get_comparison_siblings(
    session: Session, requirement: Requirement
) -> list[SiblingText]:
    doc_id = resolve_source_document_id(session, requirement)
    if doc_id is None:
        return []

    stmt = (
        select(Requirement)
        .join(
            ExtractedRequirement,
            Requirement.source_extraction_id == ExtractedRequirement.id,
        )
        .join(
            ExtractionRun,
            ExtractedRequirement.extraction_run_id == ExtractionRun.id,
        )
        .where(
            ExtractionRun.source_document_id == doc_id,
            Requirement.id != requirement.id,
            Requirement.review_status != "rejected",
        )
    )
    rows = session.execute(stmt).scalars().all()
    return [SiblingText(id=row.id, text=row.current_text) for row in rows]


def _load_rule_ids(session: Session) -> dict[str, int]:
    rows = session.execute(select(ValidationRule.code, ValidationRule.id)).all()
    found = {code: rule_id for code, rule_id in rows}
    missing = [code for code in EXPECTED_RULE_CODES if code not in found]
    if missing:
        raise ValidationConfigurationError(
            "Missing validation_rules catalog entries: " + ", ".join(missing)
        )
    return found


def _worst_result(outcomes: list[RuleOutcome]) -> str:
    return max((outcome.result for outcome in outcomes), key=lambda r: _SEVERITY_ORDER[r])


def run_validation(session: Session, requirement_id: int) -> Requirement:
    requirement = session.get(Requirement, requirement_id)
    if requirement is None:
        raise ValueError(f"Requirement {requirement_id} does not exist")

    try:
        rule_ids = _load_rule_ids(session)
        siblings = get_comparison_siblings(session, requirement)
        text = requirement.current_text

        outcomes = [
            ("DUPLICATE_NEAR", duplicate_near.evaluate(text, siblings)),
            ("AMBIGUOUS_WORDING", ambiguous_wording.evaluate(text)),
            (
                "MISSING_ACCEPTANCE_CONDITION",
                missing_acceptance_condition.evaluate(text),
            ),
            ("MISSING_ACTOR", missing_actor.evaluate(text)),
            ("POSSIBLE_CONTRADICTION", possible_contradiction.evaluate(text, siblings)),
        ]

        run = ValidationRun(
            requirement_id=requirement.id, validator_version=VALIDATOR_VERSION
        )
        session.add(run)
        session.flush()

        for code, outcome in outcomes:
            session.add(
                ValidationResult(
                    validation_run_id=run.id,
                    rule_id=rule_ids[code],
                    result=outcome.result,
                    message=outcome.message,
                    recommended_action=outcome.recommended_action,
                )
            )

        requirement.validation_state = _worst_result([o for _, o in outcomes])
        requirement.warn_acknowledged_at = None
        requirement.warn_acknowledged_by = None

        session.commit()
    except Exception:
        session.rollback()
        raise

    session.refresh(requirement)
    return requirement
