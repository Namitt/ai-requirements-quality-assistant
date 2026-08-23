from __future__ import annotations

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import Base, get_engine
from app.models import (
    AcceptanceCriterion,
    AcceptanceCriterionEdit,
    ExtractedAcceptanceCriterion,
    ExtractedRequirement,
    ExtractionRun,
    Requirement,
    RequirementEdit,
    SourceDocument,
    ValidationResult,
    ValidationRule,
    ValidationRun,
)

EXPECTED_TABLES = {
    "source_documents",
    "extraction_runs",
    "extracted_requirements",
    "requirements",
    "requirement_edits",
    "validation_rules",
    "validation_runs",
    "validation_results",
    "extracted_acceptance_criteria",
    "acceptance_criteria",
    "acceptance_criteria_edits",
}


@pytest.fixture()
def session(tmp_path):
    db_path = tmp_path / "test.db"
    engine = get_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session
    engine.dispose()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def make_source_document(session: Session) -> SourceDocument:
    doc = SourceDocument(raw_text="The system shall do X.")
    session.add(doc)
    session.flush()
    return doc


def make_extraction_run(
    session: Session,
    doc: SourceDocument,
    mode: str = "live",
    replayed_from_run_id: int | None = None,
) -> ExtractionRun:
    run = ExtractionRun(
        source_document_id=doc.id,
        model_name="test-model",
        prompt_version="v1",
        mode=mode,
        replayed_from_run_id=replayed_from_run_id,
    )
    session.add(run)
    session.flush()
    return run


def make_extracted_requirement(
    session: Session, run: ExtractionRun
) -> ExtractedRequirement:
    extracted = ExtractedRequirement(
        extraction_run_id=run.id,
        requirement_text="The system shall do X.",
        source_span_start=0,
        source_span_end=23,
        source_quote="The system shall do X.",
    )
    session.add(extracted)
    session.flush()
    return extracted


def make_requirement(
    session: Session,
    extracted: ExtractedRequirement | None = None,
    origin: str = "ai_generated",
    **overrides,
) -> Requirement:
    kwargs = dict(
        source_extraction_id=extracted.id if extracted else None,
        current_text="The system shall do X.",
        origin=origin,
    )
    kwargs.update(overrides)
    requirement = Requirement(**kwargs)
    session.add(requirement)
    session.flush()
    return requirement


def make_validation_rule(session: Session, code: str = "DUPLICATE_NEAR") -> ValidationRule:
    rule = ValidationRule(
        code=code,
        name=code.title(),
        description="test rule",
        default_severity="warn",
    )
    session.add(rule)
    session.flush()
    return rule


def make_validation_run(session: Session, requirement: Requirement) -> ValidationRun:
    run = ValidationRun(requirement_id=requirement.id, validator_version="0.1")
    session.add(run)
    session.flush()
    return run


def full_ai_chain(session: Session) -> tuple[SourceDocument, ExtractionRun, ExtractedRequirement, Requirement]:
    doc = make_source_document(session)
    run = make_extraction_run(session, doc)
    extracted = make_extracted_requirement(session, run)
    requirement = make_requirement(session, extracted)
    return doc, run, extracted, requirement


# ---------------------------------------------------------------------------
# 1. table creation
# ---------------------------------------------------------------------------


def test_all_tables_created(session):
    inspector = inspect(session.get_bind())
    assert EXPECTED_TABLES.issubset(set(inspector.get_table_names()))


# ---------------------------------------------------------------------------
# 2. foreign keys reject missing parents
# ---------------------------------------------------------------------------


def test_extraction_run_rejects_missing_source_document(session):
    run = ExtractionRun(
        source_document_id=999,
        model_name="m",
        prompt_version="v1",
        mode="live",
    )
    session.add(run)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_extracted_requirement_rejects_missing_extraction_run(session):
    extracted = ExtractedRequirement(
        extraction_run_id=999,
        requirement_text="x",
        source_span_start=0,
        source_span_end=1,
        source_quote="x",
    )
    session.add(extracted)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_requirement_rejects_missing_source_extraction(session):
    session.add(
        Requirement(source_extraction_id=999, current_text="x", origin="ai_generated")
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_validation_result_rejects_missing_rule(session):
    _, _, _, requirement = full_ai_chain(session)
    run = make_validation_run(session, requirement)
    session.add(
        ValidationResult(
            validation_run_id=run.id, rule_id=999, result="pass", message="ok"
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


# ---------------------------------------------------------------------------
# 3 & 4. valid / invalid enum and CHECK values
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["live", "replay"])
def test_valid_mode_accepted(session, mode):
    doc = make_source_document(session)
    replayed_from = None
    if mode == "replay":
        live_run = make_extraction_run(session, doc, mode="live")
        replayed_from = live_run.id
    make_extraction_run(session, doc, mode=mode, replayed_from_run_id=replayed_from)


def test_invalid_mode_rejected(session):
    doc = make_source_document(session)
    run = ExtractionRun(
        source_document_id=doc.id,
        model_name="m",
        prompt_version="v1",
        mode="bogus",
    )
    session.add(run)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


@pytest.mark.parametrize("origin", ["ai_generated", "manual"])
def test_valid_origin_accepted(session, origin):
    make_requirement(session, origin=origin)


def test_invalid_origin_rejected(session):
    with pytest.raises(IntegrityError):
        make_requirement(session, origin="bogus")
    session.rollback()


@pytest.mark.parametrize(
    "state", ["not_validated", "pass", "warn", "fail"]
)
def test_valid_validation_state_accepted(session, state):
    make_requirement(session, validation_state=state)


def test_invalid_validation_state_rejected(session):
    with pytest.raises(IntegrityError):
        make_requirement(session, validation_state="bogus")
    session.rollback()


@pytest.mark.parametrize("status", ["pending", "rejected"])
def test_valid_review_status_accepted(session, status):
    make_requirement(session, review_status=status)


def test_invalid_review_status_rejected(session):
    with pytest.raises(IntegrityError):
        make_requirement(session, review_status="bogus")
    session.rollback()


@pytest.mark.parametrize("result_value", ["pass", "warn", "fail"])
def test_valid_validation_result_accepted(session, result_value):
    _, _, _, requirement = full_ai_chain(session)
    rule = make_validation_rule(session)
    run = make_validation_run(session, requirement)
    session.add(
        ValidationResult(
            validation_run_id=run.id,
            rule_id=rule.id,
            result=result_value,
            message="checked",
        )
    )
    session.flush()


def test_invalid_validation_result_rejected(session):
    _, _, _, requirement = full_ai_chain(session)
    rule = make_validation_rule(session)
    run = make_validation_run(session, requirement)
    session.add(
        ValidationResult(
            validation_run_id=run.id,
            rule_id=rule.id,
            result="bogus",
            message="checked",
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


@pytest.mark.parametrize("severity", ["warn", "fail"])
def test_valid_default_severity_accepted(session, severity):
    session.add(
        ValidationRule(
            code=f"RULE_{severity}",
            name="r",
            description="d",
            default_severity=severity,
        )
    )
    session.flush()


def test_invalid_default_severity_rejected(session):
    session.add(
        ValidationRule(
            code="RULE_BAD", name="r", description="d", default_severity="pass"
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_validation_rule_code_unique(session):
    make_validation_rule(session, code="DUPLICATE_NEAR")
    session.add(
        ValidationRule(
            code="DUPLICATE_NEAR",
            name="Duplicate again",
            description="d",
            default_severity="warn",
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


# ---------------------------------------------------------------------------
# 5-8. approval gating
# ---------------------------------------------------------------------------


def test_approved_fail_rejected(session):
    with pytest.raises(IntegrityError):
        make_requirement(
            session, validation_state="fail", review_status="approved"
        )
    session.rollback()


def test_approved_warn_without_ack_rejected(session):
    with pytest.raises(IntegrityError):
        make_requirement(
            session,
            validation_state="warn",
            review_status="approved",
            warn_acknowledged_at=None,
            warn_acknowledged_by=None,
        )
    session.rollback()


def test_approved_warn_with_ack_allowed(session):
    from datetime import datetime, timezone

    make_requirement(
        session,
        validation_state="warn",
        review_status="approved",
        warn_acknowledged_at=datetime.now(timezone.utc),
        warn_acknowledged_by="local-analyst",
    )


def test_approved_pass_allowed(session):
    make_requirement(session, validation_state="pass", review_status="approved")


def test_approved_not_validated_rejected(session):
    with pytest.raises(IntegrityError):
        make_requirement(
            session, validation_state="not_validated", review_status="approved"
        )
    session.rollback()


# ---------------------------------------------------------------------------
# 9-10. replay constraints
# ---------------------------------------------------------------------------


def test_live_run_with_no_replay_source_allowed(session):
    doc = make_source_document(session)
    make_extraction_run(session, doc, mode="live", replayed_from_run_id=None)


def test_live_run_with_replay_source_rejected(session):
    doc = make_source_document(session)
    other = make_extraction_run(session, doc, mode="live")
    with pytest.raises(IntegrityError):
        make_extraction_run(session, doc, mode="live", replayed_from_run_id=other.id)
    session.rollback()


def test_replay_run_with_replay_source_allowed(session):
    doc = make_source_document(session)
    live_run = make_extraction_run(session, doc, mode="live")
    make_extraction_run(session, doc, mode="replay", replayed_from_run_id=live_run.id)


def test_replay_run_without_replay_source_rejected(session):
    doc = make_source_document(session)
    with pytest.raises(IntegrityError):
        make_extraction_run(session, doc, mode="replay", replayed_from_run_id=None)
    session.rollback()


def test_replay_run_rejects_missing_replayed_from_run(session):
    doc = make_source_document(session)
    session.add(
        ExtractionRun(
            source_document_id=doc.id,
            model_name="m",
            prompt_version="v1",
            mode="replay",
            replayed_from_run_id=999,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


# ---------------------------------------------------------------------------
# 11-12. requirement / extraction relationship cases
# ---------------------------------------------------------------------------


def test_multiple_requirements_reference_one_extraction(session):
    doc = make_source_document(session)
    run = make_extraction_run(session, doc)
    extracted = make_extracted_requirement(session, run)
    req_a = make_requirement(session, extracted)
    req_b = make_requirement(session, extracted)
    assert req_a.id != req_b.id
    assert req_a.source_extraction_id == req_b.source_extraction_id == extracted.id


def test_manual_requirement_with_null_source_extraction(session):
    requirement = make_requirement(session, extracted=None, origin="manual")
    assert requirement.source_extraction_id is None


# ---------------------------------------------------------------------------
# 13-15. validation/edit history
# ---------------------------------------------------------------------------


def test_multiple_validation_runs_for_one_requirement(session):
    _, _, _, requirement = full_ai_chain(session)
    run_a = make_validation_run(session, requirement)
    run_b = make_validation_run(session, requirement)
    assert run_a.id != run_b.id
    assert run_a.requirement_id == run_b.requirement_id == requirement.id


def test_validation_result_linked_to_validation_run(session):
    _, _, _, requirement = full_ai_chain(session)
    rule = make_validation_rule(session)
    run = make_validation_run(session, requirement)
    result = ValidationResult(
        validation_run_id=run.id, rule_id=rule.id, result="pass", message="ok"
    )
    session.add(result)
    session.flush()
    assert result.validation_run_id == run.id


def test_validation_result_rejects_missing_validation_run(session):
    rule = make_validation_rule(session)
    session.add(
        ValidationResult(
            validation_run_id=999, rule_id=rule.id, result="pass", message="ok"
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_requirement_edit_linked_to_requirement(session):
    _, _, _, requirement = full_ai_chain(session)
    edit = RequirementEdit(
        requirement_id=requirement.id,
        previous_text="old",
        new_text="new",
        edited_by="local-analyst",
    )
    session.add(edit)
    session.flush()
    assert edit.requirement_id == requirement.id


def test_requirement_edit_rejects_missing_requirement(session):
    session.add(
        RequirementEdit(requirement_id=999, previous_text="old", new_text="new")
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


# ---------------------------------------------------------------------------
# 16. duplicate validation result per run/rule rejected
# ---------------------------------------------------------------------------


def test_duplicate_validation_result_same_run_and_rule_rejected(session):
    _, _, _, requirement = full_ai_chain(session)
    rule = make_validation_rule(session)
    run = make_validation_run(session, requirement)
    session.add(
        ValidationResult(
            validation_run_id=run.id, rule_id=rule.id, result="pass", message="ok"
        )
    )
    session.flush()
    session.add(
        ValidationResult(
            validation_run_id=run.id, rule_id=rule.id, result="warn", message="again"
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


# ---------------------------------------------------------------------------
# 17. acceptance criteria tables (Module 2)
# ---------------------------------------------------------------------------


def make_extracted_acceptance_criterion(
    session: Session,
    requirement: Requirement,
    mode: str = "live",
    replayed_from_id: int | None = None,
) -> ExtractedAcceptanceCriterion:
    extracted = ExtractedAcceptanceCriterion(
        requirement_id=requirement.id,
        criterion_text="Given X, when Y, then Z.",
        mode=mode,
        replayed_from_id=replayed_from_id,
        model_name="test-model",
        prompt_version="v1",
    )
    session.add(extracted)
    session.flush()
    return extracted


def make_acceptance_criterion(
    session: Session, extracted: ExtractedAcceptanceCriterion, **overrides
) -> AcceptanceCriterion:
    kwargs = dict(
        source_extraction_id=extracted.id,
        current_text="Given X, when Y, then Z.",
    )
    kwargs.update(overrides)
    criterion = AcceptanceCriterion(**kwargs)
    session.add(criterion)
    session.flush()
    return criterion


@pytest.mark.parametrize("mode", ["live", "replay"])
def test_ac_valid_mode_accepted(session, mode):
    _, _, _, requirement = full_ai_chain(session)
    replayed_from = None
    if mode == "replay":
        live = make_extracted_acceptance_criterion(session, requirement, mode="live")
        replayed_from = live.id
    make_extracted_acceptance_criterion(
        session, requirement, mode=mode, replayed_from_id=replayed_from
    )


def test_ac_invalid_mode_rejected(session):
    _, _, _, requirement = full_ai_chain(session)
    session.add(
        ExtractedAcceptanceCriterion(
            requirement_id=requirement.id,
            criterion_text="x",
            mode="bogus",
            model_name="m",
            prompt_version="v1",
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_ac_live_with_replay_source_rejected(session):
    _, _, _, requirement = full_ai_chain(session)
    other = make_extracted_acceptance_criterion(session, requirement, mode="live")
    with pytest.raises(IntegrityError):
        make_extracted_acceptance_criterion(
            session, requirement, mode="live", replayed_from_id=other.id
        )
    session.rollback()


def test_ac_replay_without_replay_source_rejected(session):
    _, _, _, requirement = full_ai_chain(session)
    with pytest.raises(IntegrityError):
        make_extracted_acceptance_criterion(session, requirement, mode="replay")
    session.rollback()


def test_ac_replay_source_can_be_replayed_again(session):
    _, _, _, requirement = full_ai_chain(session)
    live = make_extracted_acceptance_criterion(session, requirement, mode="live")
    make_extracted_acceptance_criterion(
        session, requirement, mode="replay", replayed_from_id=live.id
    )


@pytest.mark.parametrize("state", ["not_validated", "pass", "warn", "fail"])
def test_ac_valid_validation_state_accepted(session, state):
    _, _, _, requirement = full_ai_chain(session)
    extracted = make_extracted_acceptance_criterion(session, requirement)
    make_acceptance_criterion(session, extracted, validation_state=state)


def test_ac_invalid_validation_state_rejected(session):
    _, _, _, requirement = full_ai_chain(session)
    extracted = make_extracted_acceptance_criterion(session, requirement)
    with pytest.raises(IntegrityError):
        make_acceptance_criterion(session, extracted, validation_state="bogus")
    session.rollback()


@pytest.mark.parametrize("status", ["pending", "rejected"])
def test_ac_valid_review_status_accepted(session, status):
    _, _, _, requirement = full_ai_chain(session)
    extracted = make_extracted_acceptance_criterion(session, requirement)
    make_acceptance_criterion(session, extracted, review_status=status)


def test_ac_invalid_review_status_rejected(session):
    _, _, _, requirement = full_ai_chain(session)
    extracted = make_extracted_acceptance_criterion(session, requirement)
    with pytest.raises(IntegrityError):
        make_acceptance_criterion(session, extracted, review_status="bogus")
    session.rollback()


def test_ac_approved_fail_rejected(session):
    _, _, _, requirement = full_ai_chain(session)
    extracted = make_extracted_acceptance_criterion(session, requirement)
    with pytest.raises(IntegrityError):
        make_acceptance_criterion(
            session, extracted, validation_state="fail", review_status="approved"
        )
    session.rollback()


def test_ac_approved_warn_without_ack_rejected(session):
    _, _, _, requirement = full_ai_chain(session)
    extracted = make_extracted_acceptance_criterion(session, requirement)
    with pytest.raises(IntegrityError):
        make_acceptance_criterion(
            session,
            extracted,
            validation_state="warn",
            review_status="approved",
            warn_acknowledged_at=None,
            warn_acknowledged_by=None,
        )
    session.rollback()


def test_ac_approved_warn_with_ack_allowed(session):
    from datetime import datetime, timezone

    _, _, _, requirement = full_ai_chain(session)
    extracted = make_extracted_acceptance_criterion(session, requirement)
    make_acceptance_criterion(
        session,
        extracted,
        validation_state="warn",
        review_status="approved",
        warn_acknowledged_at=datetime.now(timezone.utc),
        warn_acknowledged_by="local-analyst",
    )


def test_ac_approved_pass_allowed(session):
    _, _, _, requirement = full_ai_chain(session)
    extracted = make_extracted_acceptance_criterion(session, requirement)
    make_acceptance_criterion(
        session, extracted, validation_state="pass", review_status="approved"
    )


def test_ac_approved_not_validated_rejected(session):
    _, _, _, requirement = full_ai_chain(session)
    extracted = make_extracted_acceptance_criterion(session, requirement)
    with pytest.raises(IntegrityError):
        make_acceptance_criterion(
            session,
            extracted,
            validation_state="not_validated",
            review_status="approved",
        )
    session.rollback()


def test_acceptance_criterion_edit_linked(session):
    _, _, _, requirement = full_ai_chain(session)
    extracted = make_extracted_acceptance_criterion(session, requirement)
    criterion = make_acceptance_criterion(session, extracted)
    edit = AcceptanceCriterionEdit(
        acceptance_criterion_id=criterion.id,
        previous_text="old",
        new_text="new",
        edited_by="local-analyst",
    )
    session.add(edit)
    session.flush()
    assert edit.acceptance_criterion_id == criterion.id


def test_acceptance_criterion_edit_rejects_missing_criterion(session):
    session.add(
        AcceptanceCriterionEdit(
            acceptance_criterion_id=999, previous_text="old", new_text="new"
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


# ---------------------------------------------------------------------------
# 18. validation_runs exactly-one-parent CHECK (shared table, Module 1 + 2)
# ---------------------------------------------------------------------------


def test_validation_run_requirement_only_still_valid(session):
    _, _, _, requirement = full_ai_chain(session)
    run = ValidationRun(requirement_id=requirement.id, validator_version="1.0.0")
    session.add(run)
    session.flush()
    assert run.requirement_id == requirement.id
    assert run.acceptance_criterion_id is None


def test_validation_run_acceptance_criterion_only_valid(session):
    _, _, _, requirement = full_ai_chain(session)
    extracted = make_extracted_acceptance_criterion(session, requirement)
    criterion = make_acceptance_criterion(session, extracted)
    run = ValidationRun(acceptance_criterion_id=criterion.id, validator_version="1.0.0")
    session.add(run)
    session.flush()
    assert run.acceptance_criterion_id == criterion.id
    assert run.requirement_id is None


def test_validation_run_both_null_rejected(session):
    session.add(ValidationRun(validator_version="1.0.0"))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_validation_run_both_populated_rejected(session):
    _, _, _, requirement = full_ai_chain(session)
    extracted = make_extracted_acceptance_criterion(session, requirement)
    criterion = make_acceptance_criterion(session, extracted)
    session.add(
        ValidationRun(
            requirement_id=requirement.id,
            acceptance_criterion_id=criterion.id,
            validator_version="1.0.0",
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()
