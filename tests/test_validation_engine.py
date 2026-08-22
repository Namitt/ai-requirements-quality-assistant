from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db import Base, get_engine
from app.models import (
    ExtractedRequirement,
    ExtractionRun,
    Requirement,
    SourceDocument,
    ValidationResult,
    ValidationRule,
    ValidationRun,
)
from app.seed import seed_validation_rules
from app.validation_engine import (
    EXPECTED_RULE_CODES,
    VALIDATOR_VERSION,
    ValidationConfigurationError,
    get_comparison_siblings,
    run_validation,
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


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def make_source_document(session: Session, raw_text: str = "source text") -> SourceDocument:
    doc = SourceDocument(raw_text=raw_text)
    session.add(doc)
    session.flush()
    return doc


def make_extraction_run(session: Session, doc: SourceDocument, mode: str = "live", **kw) -> ExtractionRun:
    run = ExtractionRun(
        source_document_id=doc.id,
        model_name="test-model",
        prompt_version="v1",
        mode=mode,
        **kw,
    )
    session.add(run)
    session.flush()
    return run


def make_extracted_requirement(session: Session, run: ExtractionRun, text: str) -> ExtractedRequirement:
    extracted = ExtractedRequirement(
        extraction_run_id=run.id,
        requirement_text=text,
        source_span_start=0,
        source_span_end=len(text),
        source_quote=text,
    )
    session.add(extracted)
    session.flush()
    return extracted


def make_ai_requirement(
    session: Session, extraction_run: ExtractionRun, text: str, **overrides
) -> Requirement:
    extracted = make_extracted_requirement(session, extraction_run, text)
    kwargs = dict(source_extraction_id=extracted.id, current_text=text, origin="ai_generated")
    kwargs.update(overrides)
    req = Requirement(**kwargs)
    session.add(req)
    session.flush()
    return req


def make_manual_requirement(session: Session, text: str, **overrides) -> Requirement:
    kwargs = dict(source_extraction_id=None, current_text=text, origin="manual")
    kwargs.update(overrides)
    req = Requirement(**kwargs)
    session.add(req)
    session.flush()
    return req


TEXT_A = "The system shall lock a user account after 5 failed login attempts."
TEXT_A_NEAR_DUP = "The system shall lock a user account after 5 failed login attempt."


# ---------------------------------------------------------------------------
# comparison scope
# ---------------------------------------------------------------------------


def test_manual_requirement_excluded_from_comparison_scope(session):
    doc = make_source_document(session)
    run = make_extraction_run(session, doc)
    make_ai_requirement(session, run, TEXT_A_NEAR_DUP)
    manual = make_manual_requirement(session, TEXT_A)

    siblings = get_comparison_siblings(session, manual)
    assert siblings == []


def test_manual_requirement_never_appears_as_a_sibling(session):
    doc = make_source_document(session)
    run = make_extraction_run(session, doc)
    ai_req = make_ai_requirement(session, run, TEXT_A)
    make_manual_requirement(session, TEXT_A_NEAR_DUP)

    siblings = get_comparison_siblings(session, ai_req)
    assert siblings == []


def test_document_wide_comparison_spans_multiple_extraction_runs(session):
    doc = make_source_document(session)
    run1 = make_extraction_run(session, doc)
    run2 = make_extraction_run(session, doc)
    req1 = make_ai_requirement(session, run1, TEXT_A)
    req2 = make_ai_requirement(session, run2, TEXT_A_NEAR_DUP)

    siblings = get_comparison_siblings(session, req1)
    assert [s.id for s in siblings] == [req2.id]


def test_requirements_from_different_documents_are_not_compared(session):
    doc1 = make_source_document(session, "doc one")
    doc2 = make_source_document(session, "doc two")
    run1 = make_extraction_run(session, doc1)
    run2 = make_extraction_run(session, doc2)
    req1 = make_ai_requirement(session, run1, TEXT_A)
    make_ai_requirement(session, run2, TEXT_A_NEAR_DUP)

    siblings = get_comparison_siblings(session, req1)
    assert siblings == []


def test_rejected_sibling_excluded_from_comparison_scope(session):
    doc = make_source_document(session)
    run = make_extraction_run(session, doc)
    req1 = make_ai_requirement(session, run, TEXT_A)
    make_ai_requirement(session, run, TEXT_A_NEAR_DUP, review_status="rejected")

    siblings = get_comparison_siblings(session, req1)
    assert siblings == []


# ---------------------------------------------------------------------------
# run_validation — basic shape
# ---------------------------------------------------------------------------


def test_successful_run_creates_exactly_one_run_and_five_results(session):
    doc = make_source_document(session)
    run = make_extraction_run(session, doc)
    req = make_ai_requirement(session, run, TEXT_A)

    run_validation(session, req.id)

    runs = session.query(ValidationRun).filter_by(requirement_id=req.id).all()
    assert len(runs) == 1
    results = session.query(ValidationResult).filter_by(validation_run_id=runs[0].id).all()
    assert len(results) == 5
    codes = {
        session.get(ValidationRule, r.rule_id).code for r in results
    }
    assert codes == set(EXPECTED_RULE_CODES)


def test_validator_version_recorded(session):
    doc = make_source_document(session)
    run = make_extraction_run(session, doc)
    req = make_ai_requirement(session, run, TEXT_A)

    run_validation(session, req.id)

    validation_run = session.query(ValidationRun).filter_by(requirement_id=req.id).one()
    assert validation_run.validator_version == VALIDATOR_VERSION == "1.0.0"


def test_validation_state_derived_as_worst_result(session):
    doc = make_source_document(session)
    run = make_extraction_run(session, doc)
    # triggers MISSING_ACCEPTANCE_CONDITION and MISSING_ACTOR warnings, no fail
    req = make_ai_requirement(session, run, "Reports shall be exportable.")

    updated = run_validation(session, req.id)

    assert updated.validation_state == "warn"


def test_validation_state_pass_when_all_rules_clean(session):
    doc = make_source_document(session)
    run = make_extraction_run(session, doc)
    req = make_ai_requirement(
        session,
        run,
        "The system shall lock a user account after 5 failed login attempts within 10 minutes.",
    )

    updated = run_validation(session, req.id)

    assert updated.validation_state == "pass"


def test_validation_state_fail_when_duplicate_near_fail_tier(session):
    doc = make_source_document(session)
    run = make_extraction_run(session, doc)
    req1 = make_ai_requirement(session, run, TEXT_A)
    req2 = make_ai_requirement(session, run, TEXT_A_NEAR_DUP)

    updated = run_validation(session, req2.id)

    assert updated.validation_state == "fail"


# ---------------------------------------------------------------------------
# acknowledgement reset
# ---------------------------------------------------------------------------


def test_acknowledgement_reset_on_new_validation_run(session):
    from datetime import datetime, timezone

    doc = make_source_document(session)
    run = make_extraction_run(session, doc)
    req = make_ai_requirement(
        session,
        run,
        "Reports shall be exportable.",
        validation_state="warn",
        warn_acknowledged_at=datetime.now(timezone.utc),
        warn_acknowledged_by="local-analyst",
    )

    updated = run_validation(session, req.id)

    assert updated.warn_acknowledged_at is None
    assert updated.warn_acknowledged_by is None


# ---------------------------------------------------------------------------
# append-only history
# ---------------------------------------------------------------------------


def test_repeated_validation_creates_new_history_not_overwrite(session):
    doc = make_source_document(session)
    run = make_extraction_run(session, doc)
    req = make_ai_requirement(session, run, TEXT_A)

    run_validation(session, req.id)
    run_validation(session, req.id)

    runs = session.query(ValidationRun).filter_by(requirement_id=req.id).all()
    assert len(runs) == 2
    results = (
        session.query(ValidationResult)
        .filter(ValidationResult.validation_run_id.in_([r.id for r in runs]))
        .all()
    )
    assert len(results) == 10


# ---------------------------------------------------------------------------
# atomicity
# ---------------------------------------------------------------------------


def test_atomic_rollback_when_a_rule_raises(session):
    doc = make_source_document(session)
    run = make_extraction_run(session, doc)
    req = make_ai_requirement(session, run, TEXT_A)
    session.commit()
    req_id = req.id

    with patch(
        "app.validation_engine.ambiguous_wording.evaluate",
        side_effect=RuntimeError("boom"),
    ):
        with pytest.raises(RuntimeError):
            run_validation(session, req_id)

    assert session.query(ValidationRun).filter_by(requirement_id=req_id).count() == 0
    assert session.query(ValidationResult).count() == 0
    reloaded = session.get(Requirement, req_id)
    assert reloaded.validation_state == "not_validated"


# ---------------------------------------------------------------------------
# missing catalog configuration
# ---------------------------------------------------------------------------


def test_missing_validation_rule_fails_the_transaction(session):
    doc = make_source_document(session)
    run = make_extraction_run(session, doc)
    req = make_ai_requirement(session, run, TEXT_A)

    session.execute(delete(ValidationRule).where(ValidationRule.code == "MISSING_ACTOR"))
    session.commit()

    with pytest.raises(ValidationConfigurationError):
        run_validation(session, req.id)

    assert session.query(ValidationRun).filter_by(requirement_id=req.id).count() == 0
