from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AcceptanceCriterion, ValidationResult, ValidationRule, ValidationRun
from app.rules import RuleOutcome
from app.rules import ac_given_present, ac_measurable_then, ac_then_present, ac_when_present
from app.validation_engine import ValidationConfigurationError

AC_VALIDATOR_VERSION = "1.0.0"

EXPECTED_AC_RULE_CODES = (
    "AC_GIVEN_PRESENT",
    "AC_WHEN_PRESENT",
    "AC_THEN_PRESENT",
    "AC_MEASURABLE_THEN",
)

_SEVERITY_ORDER = {"pass": 0, "warn": 1, "fail": 2}


def _load_ac_rule_ids(session: Session) -> dict[str, int]:
    rows = session.execute(select(ValidationRule.code, ValidationRule.id)).all()
    found = {code: rule_id for code, rule_id in rows}
    missing = [code for code in EXPECTED_AC_RULE_CODES if code not in found]
    if missing:
        raise ValidationConfigurationError(
            "Missing validation_rules catalog entries: " + ", ".join(missing)
        )
    return found


def _worst_result(outcomes: list[RuleOutcome]) -> str:
    return max((outcome.result for outcome in outcomes), key=lambda r: _SEVERITY_ORDER[r])


def run_acceptance_criteria_validation(
    session: Session, acceptance_criterion_id: int
) -> AcceptanceCriterion:
    criterion = session.get(AcceptanceCriterion, acceptance_criterion_id)
    if criterion is None:
        raise ValueError(f"Acceptance criterion {acceptance_criterion_id} does not exist")

    try:
        rule_ids = _load_ac_rule_ids(session)
        text = criterion.current_text

        outcomes = [
            ("AC_GIVEN_PRESENT", ac_given_present.evaluate(text)),
            ("AC_WHEN_PRESENT", ac_when_present.evaluate(text)),
            ("AC_THEN_PRESENT", ac_then_present.evaluate(text)),
            ("AC_MEASURABLE_THEN", ac_measurable_then.evaluate(text)),
        ]

        run = ValidationRun(
            acceptance_criterion_id=criterion.id, validator_version=AC_VALIDATOR_VERSION
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

        criterion.validation_state = _worst_result([o for _, o in outcomes])
        criterion.warn_acknowledged_at = None
        criterion.warn_acknowledged_by = None

        session.commit()
    except Exception:
        session.rollback()
        raise

    session.refresh(criterion)
    return criterion
