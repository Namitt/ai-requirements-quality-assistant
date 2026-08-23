from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.acceptance_criteria_validation_engine import (
    AC_VALIDATOR_VERSION,
    EXPECTED_AC_RULE_CODES,
    run_acceptance_criteria_validation,
)
from app.db import Base, get_engine
from app.models import (
    AcceptanceCriterion,
    ExtractedAcceptanceCriterion,
    Requirement,
    ValidationResult,
    ValidationRule,
    ValidationRun,
)
from app.rules import ac_measurable_then
from app.seed import seed_validation_rules
from app.validation_engine import EXPECTED_RULE_CODES, run_validation

FULL_VALID = (
    "Given a user with 5 failed login attempts, when they attempt to log in "
    "again, then the system shall lock the account within 2 seconds."
)
NO_GIVEN = (
    "When the user attempts to log in again, then the system shall lock the "
    "account within 2 seconds."
)
NO_WHEN = (
    "Given a user with 5 failed login attempts, then the system shall lock "
    "the account within 2 seconds."
)
NO_THEN = (
    "Given a user with 5 failed login attempts, when they attempt to log in "
    "again."
)
THEN_NOT_MEASURABLE = (
    "Given a user with 5 failed login attempts, when they attempt to log in "
    "again, then the system shall lock the account."
)


@pytest.fixture()
def session(tmp_path):
    db_path = tmp_path / "test.db"
    engine = get_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        seed_validation_rules(db_session)
        yield db_session
    engine.dispose()


def make_requirement(session: Session, text: str = "The system shall do X.") -> Requirement:
    requirement = Requirement(current_text=text, origin="ai_generated")
    session.add(requirement)
    session.flush()
    return requirement


def make_acceptance_criterion(session: Session, text: str) -> AcceptanceCriterion:
    requirement = make_requirement(session)
    extracted = ExtractedAcceptanceCriterion(
        requirement_id=requirement.id,
        criterion_text=text,
        mode="live",
        model_name="test-model",
        prompt_version="v1",
    )
    session.add(extracted)
    session.flush()
    criterion = AcceptanceCriterion(source_extraction_id=extracted.id, current_text=text)
    session.add(criterion)
    session.commit()
    return criterion


def _result_for(session: Session, criterion_id: int, code: str) -> str:
    run = (
        session.query(ValidationRun)
        .filter_by(acceptance_criterion_id=criterion_id)
        .order_by(ValidationRun.id.desc())
        .first()
    )
    rule = session.query(ValidationRule).filter_by(code=code).one()
    result = (
        session.query(ValidationResult)
        .filter_by(validation_run_id=run.id, rule_id=rule.id)
        .one()
    )
    return result.result


# ---------------------------------------------------------------------------
# each rule independently
# ---------------------------------------------------------------------------


def test_all_four_rules_pass_on_fully_formed_criterion(session):
    criterion = make_acceptance_criterion(session, FULL_VALID)
    run_acceptance_criteria_validation(session, criterion.id)

    for code in EXPECTED_AC_RULE_CODES:
        assert _result_for(session, criterion.id, code) == "pass"


def test_ac_given_present_warns_when_given_missing(session):
    criterion = make_acceptance_criterion(session, NO_GIVEN)
    run_acceptance_criteria_validation(session, criterion.id)

    assert _result_for(session, criterion.id, "AC_GIVEN_PRESENT") == "warn"
    assert _result_for(session, criterion.id, "AC_WHEN_PRESENT") == "pass"
    assert _result_for(session, criterion.id, "AC_THEN_PRESENT") == "pass"


def test_ac_when_present_warns_when_when_missing(session):
    criterion = make_acceptance_criterion(session, NO_WHEN)
    run_acceptance_criteria_validation(session, criterion.id)

    assert _result_for(session, criterion.id, "AC_GIVEN_PRESENT") == "pass"
    assert _result_for(session, criterion.id, "AC_WHEN_PRESENT") == "warn"
    assert _result_for(session, criterion.id, "AC_THEN_PRESENT") == "pass"


def test_ac_then_present_and_measurable_both_warn_independently_when_then_missing(session):
    criterion = make_acceptance_criterion(session, NO_THEN)
    run_acceptance_criteria_validation(session, criterion.id)

    assert _result_for(session, criterion.id, "AC_THEN_PRESENT") == "warn"
    assert _result_for(session, criterion.id, "AC_MEASURABLE_THEN") == "warn"


def test_ac_measurable_then_warns_when_then_present_but_not_measurable(session):
    criterion = make_acceptance_criterion(session, THEN_NOT_MEASURABLE)
    run_acceptance_criteria_validation(session, criterion.id)

    assert _result_for(session, criterion.id, "AC_THEN_PRESENT") == "pass"
    assert _result_for(session, criterion.id, "AC_MEASURABLE_THEN") == "warn"


# ---------------------------------------------------------------------------
# AC_MEASURABLE_THEN - Then-clause boundary (direct rule unit tests)
# ---------------------------------------------------------------------------


def test_measurable_then_evidence_in_first_then_passes():
    text = (
        "Given a user with 5 failed login attempts, when they attempt to "
        "log in again, then the system shall lock the account within 2 "
        "seconds."
    )
    assert ac_measurable_then.evaluate(text).result == "pass"


def test_measurable_then_no_evidence_in_first_then_warns():
    text = (
        "Given a user with 5 failed login attempts, when they attempt to "
        "log in again, then the system shall lock the account."
    )
    assert ac_measurable_then.evaluate(text).result == "warn"


def test_measurable_then_evidence_only_in_second_scenario_does_not_leak():
    text = (
        "Given A, when B, then nothing happens. Given C, when D, then the "
        "value is at least 5."
    )
    assert ac_measurable_then.evaluate(text).result == "warn"


def test_measurable_then_trailing_prose_does_not_leak():
    text = (
        "Given A, when B, then C happens. Note: when this occurs later, "
        "escalate to 5 people."
    )
    assert ac_measurable_then.evaluate(text).result == "warn"


def test_measurable_then_single_scenario_behaviour_unchanged():
    no_signal = "Given A, when B, then C happens."
    with_signal = "Given A, when B, then the count shall not exceed 10 items."
    assert ac_measurable_then.evaluate(no_signal).result == "warn"
    assert ac_measurable_then.evaluate(with_signal).result == "pass"


@pytest.mark.parametrize(
    "text",
    [FULL_VALID, NO_GIVEN, NO_WHEN, NO_THEN, THEN_NOT_MEASURABLE, ""],
    ids=["full_valid", "no_given", "no_when", "no_then", "then_not_measurable", "empty"],
)
def test_no_ac_rule_ever_produces_fail(session, text):
    criterion = make_acceptance_criterion(session, text)
    run_acceptance_criteria_validation(session, criterion.id)
    for code in EXPECTED_AC_RULE_CODES:
        assert _result_for(session, criterion.id, code) != "fail"


# ---------------------------------------------------------------------------
# aggregation / run shape
# ---------------------------------------------------------------------------


def test_worst_result_aggregation_is_warn_when_any_rule_warns(session):
    criterion = make_acceptance_criterion(session, NO_GIVEN)
    updated = run_acceptance_criteria_validation(session, criterion.id)
    assert updated.validation_state == "warn"


def test_validation_state_pass_when_all_rules_clean(session):
    criterion = make_acceptance_criterion(session, FULL_VALID)
    updated = run_acceptance_criteria_validation(session, criterion.id)
    assert updated.validation_state == "pass"


def test_successful_run_creates_exactly_one_run_and_four_results(session):
    criterion = make_acceptance_criterion(session, FULL_VALID)

    run_acceptance_criteria_validation(session, criterion.id)

    runs = session.query(ValidationRun).filter_by(acceptance_criterion_id=criterion.id).all()
    assert len(runs) == 1
    results = session.query(ValidationResult).filter_by(validation_run_id=runs[0].id).all()
    assert len(results) == 4
    codes = {session.get(ValidationRule, r.rule_id).code for r in results}
    assert codes == set(EXPECTED_AC_RULE_CODES)


def test_validator_version_recorded(session):
    criterion = make_acceptance_criterion(session, FULL_VALID)

    run_acceptance_criteria_validation(session, criterion.id)

    run = session.query(ValidationRun).filter_by(acceptance_criterion_id=criterion.id).one()
    assert run.validator_version == AC_VALIDATOR_VERSION


def test_validation_run_parent_linkage_uses_acceptance_criterion_id(session):
    criterion = make_acceptance_criterion(session, FULL_VALID)

    run_acceptance_criteria_validation(session, criterion.id)

    run = session.query(ValidationRun).filter_by(acceptance_criterion_id=criterion.id).one()
    assert run.acceptance_criterion_id == criterion.id
    assert run.requirement_id is None


def test_acknowledgement_reset_on_new_validation_run(session):
    from datetime import datetime, timezone

    criterion = make_acceptance_criterion(session, NO_GIVEN)
    criterion.warn_acknowledged_at = datetime.now(timezone.utc)
    criterion.warn_acknowledged_by = "local-analyst"
    session.commit()

    updated = run_acceptance_criteria_validation(session, criterion.id)

    assert updated.warn_acknowledged_at is None
    assert updated.warn_acknowledged_by is None


def test_repeated_validation_creates_new_history_not_overwrite(session):
    criterion = make_acceptance_criterion(session, FULL_VALID)

    run_acceptance_criteria_validation(session, criterion.id)
    run_acceptance_criteria_validation(session, criterion.id)

    runs = session.query(ValidationRun).filter_by(acceptance_criterion_id=criterion.id).all()
    assert len(runs) == 2
    results = (
        session.query(ValidationResult)
        .filter(ValidationResult.validation_run_id.in_([r.id for r in runs]))
        .all()
    )
    assert len(results) == 8


# ---------------------------------------------------------------------------
# atomicity
# ---------------------------------------------------------------------------


def test_atomic_rollback_when_a_rule_raises(session):
    criterion = make_acceptance_criterion(session, FULL_VALID)
    criterion_id = criterion.id

    with patch(
        "app.acceptance_criteria_validation_engine.ac_given_present.evaluate",
        side_effect=RuntimeError("boom"),
    ):
        with pytest.raises(RuntimeError):
            run_acceptance_criteria_validation(session, criterion_id)

    assert (
        session.query(ValidationRun).filter_by(acceptance_criterion_id=criterion_id).count()
        == 0
    )
    reloaded = session.get(AcceptanceCriterion, criterion_id)
    assert reloaded.validation_state == "not_validated"


# ---------------------------------------------------------------------------
# regression: existing requirement validation is unaffected
# ---------------------------------------------------------------------------


def test_requirement_validation_still_produces_exactly_five_results(session):
    requirement = make_requirement(
        session, "The system shall lock a user account after 5 failed login attempts."
    )
    session.commit()

    run_validation(session, requirement.id)

    runs = session.query(ValidationRun).filter_by(requirement_id=requirement.id).all()
    assert len(runs) == 1
    results = session.query(ValidationResult).filter_by(validation_run_id=runs[0].id).all()
    assert len(results) == 5
    codes = {session.get(ValidationRule, r.rule_id).code for r in results}
    assert codes == set(EXPECTED_RULE_CODES)
    assert not (codes & set(EXPECTED_AC_RULE_CODES))
    run = runs[0]
    assert run.requirement_id == requirement.id
    assert run.acceptance_criterion_id is None
