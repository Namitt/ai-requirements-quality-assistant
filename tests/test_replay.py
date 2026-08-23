from __future__ import annotations

import json

import pytest
from sqlalchemy.orm import Session

from app.db import Base, get_engine
from app.extraction import ExtractionCallResult
from app.extraction_engine import (
    ReplaySourceNotFoundError,
    ReplaySourceNotLiveError,
    run_extraction,
    run_replay,
)
from app.models import (
    ExtractedRequirement,
    ExtractionRun,
    Requirement,
    ValidationRun,
)
from app.seed import seed_validation_rules

SOURCE_TEXT = (
    "The system shall lock a user account after 5 failed login attempts. "
    "The system shall export monthly reports as CSV."
)


class FakeExtractionClient:
    def __init__(self, payload, model_name: str = "fake-model-v1"):
        self.model_name = model_name
        self._text = payload if isinstance(payload, str) else json.dumps(payload)

    def complete(self, prompt: str) -> ExtractionCallResult:
        return ExtractionCallResult(text=self._text, raw_response=self._text)


@pytest.fixture()
def session(tmp_path):
    db_path = tmp_path / "test.db"
    engine = get_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        seed_validation_rules(db_session)
        yield db_session
    engine.dispose()


def _make_live_run(session: Session, requirements=None) -> ExtractionRun:
    payload = {
        "requirements": requirements
        if requirements is not None
        else [
            {
                "requirement_text": "The system shall lock a user account after 5 failed login attempts.",
                "source_quote": "The system shall lock a user account after 5 failed login attempts.",
            },
            {
                "requirement_text": "The system shall export monthly reports as CSV.",
                "source_quote": "The system shall export monthly reports as CSV.",
            },
        ]
    }
    client = FakeExtractionClient(payload, model_name="claude-sonnet-5-test")
    return run_extraction(session, client, SOURCE_TEXT, title="Original call notes")


# ---------------------------------------------------------------------------
# successful replay
# ---------------------------------------------------------------------------


def test_replay_creates_a_new_extraction_run(session):
    live_run = _make_live_run(session)

    replay_run = run_replay(session, live_run.id)

    assert replay_run.id is not None
    assert replay_run.id != live_run.id


def test_replay_run_has_mode_replay(session):
    live_run = _make_live_run(session)

    replay_run = run_replay(session, live_run.id)

    assert replay_run.mode == "replay"


def test_replayed_from_run_id_points_to_original(session):
    live_run = _make_live_run(session)

    replay_run = run_replay(session, live_run.id)

    assert replay_run.replayed_from_run_id == live_run.id


def test_model_name_copied_exactly(session):
    live_run = _make_live_run(session)

    replay_run = run_replay(session, live_run.id)

    assert replay_run.model_name == live_run.model_name == "claude-sonnet-5-test"


def test_prompt_version_copied_exactly(session):
    live_run = _make_live_run(session)

    replay_run = run_replay(session, live_run.id)

    assert replay_run.prompt_version == live_run.prompt_version


def test_source_document_relationship_correct(session):
    live_run = _make_live_run(session)

    replay_run = run_replay(session, live_run.id)

    assert replay_run.source_document_id == live_run.source_document_id


def test_raw_response_not_copied_since_no_api_call_was_made(session):
    live_run = _make_live_run(session)

    replay_run = run_replay(session, live_run.id)

    assert live_run.raw_response is not None
    assert replay_run.raw_response is None


# ---------------------------------------------------------------------------
# provenance copying
# ---------------------------------------------------------------------------


def test_extracted_requirement_text_copied_exactly(session):
    live_run = _make_live_run(session)

    run_replay(session, live_run.id)

    originals = (
        session.query(ExtractedRequirement).filter_by(extraction_run_id=live_run.id).all()
    )
    copies = (
        session.query(ExtractedRequirement)
        .filter(ExtractedRequirement.extraction_run_id != live_run.id)
        .all()
    )
    assert sorted(o.requirement_text for o in originals) == sorted(
        c.requirement_text for c in copies
    )


def test_source_quote_and_span_copied_exactly(session):
    live_run = _make_live_run(session)

    replay_run = run_replay(session, live_run.id)

    originals = {
        o.requirement_text: o
        for o in session.query(ExtractedRequirement)
        .filter_by(extraction_run_id=live_run.id)
        .all()
    }
    copies = (
        session.query(ExtractedRequirement).filter_by(extraction_run_id=replay_run.id).all()
    )
    assert len(copies) == len(originals)
    for copy in copies:
        original = originals[copy.requirement_text]
        assert copy.source_quote == original.source_quote
        assert copy.source_span_start == original.source_span_start
        assert copy.source_span_end == original.source_span_end


def test_copied_extracted_requirements_have_fresh_ids(session):
    live_run = _make_live_run(session)
    original_ids = {
        o.id for o in session.query(ExtractedRequirement).filter_by(extraction_run_id=live_run.id).all()
    }

    replay_run = run_replay(session, live_run.id)

    copy_ids = {
        c.id for c in session.query(ExtractedRequirement).filter_by(extraction_run_id=replay_run.id).all()
    }
    assert original_ids.isdisjoint(copy_ids)
    assert len(copy_ids) == len(original_ids)


def test_fresh_requirements_have_fresh_ids(session):
    live_run = _make_live_run(session)
    original_requirement_ids = {r.id for r in session.query(Requirement).all()}

    run_replay(session, live_run.id)

    all_requirement_ids = {r.id for r in session.query(Requirement).all()}
    new_ids = all_requirement_ids - original_requirement_ids
    assert len(new_ids) == 2  # two candidates in the fixture live run


def test_original_live_extraction_completely_unchanged(session):
    live_run = _make_live_run(session)
    original_model_name = live_run.model_name
    original_extracted_count = (
        session.query(ExtractedRequirement).filter_by(extraction_run_id=live_run.id).count()
    )
    original_texts = sorted(
        o.requirement_text
        for o in session.query(ExtractedRequirement).filter_by(extraction_run_id=live_run.id).all()
    )

    run_replay(session, live_run.id)
    session.refresh(live_run)

    assert live_run.mode == "live"
    assert live_run.model_name == original_model_name
    assert (
        session.query(ExtractedRequirement).filter_by(extraction_run_id=live_run.id).count()
        == original_extracted_count
    )
    assert (
        sorted(
            o.requirement_text
            for o in session.query(ExtractedRequirement)
            .filter_by(extraction_run_id=live_run.id)
            .all()
        )
        == original_texts
    )


# ---------------------------------------------------------------------------
# automatic validation
# ---------------------------------------------------------------------------


def test_replay_requirements_are_automatically_validated(session):
    live_run = _make_live_run(session)

    replay_run = run_replay(session, live_run.id)

    copied_requirement_ids = [
        req.id
        for extracted in session.query(ExtractedRequirement)
        .filter_by(extraction_run_id=replay_run.id)
        .all()
        for req in session.query(Requirement)
        .filter_by(source_extraction_id=extracted.id)
        .all()
    ]
    assert len(copied_requirement_ids) == 2
    for requirement_id in copied_requirement_ids:
        requirement = session.get(Requirement, requirement_id)
        assert requirement.validation_state in ("pass", "warn", "fail")
        run_count = (
            session.query(ValidationRun).filter_by(requirement_id=requirement_id).count()
        )
        assert run_count == 1


def test_replay_produces_expected_validation_results(session):
    # Duplicate near-identical candidates in the same live run should
    # produce a FAIL on DUPLICATE_NEAR for the replayed copies too, since
    # they land in the same source document as each other.
    live_run = _make_live_run(
        session,
        requirements=[
            {
                "requirement_text": "The system shall lock a user account after 5 failed login attempts.",
                "source_quote": "The system shall lock a user account after 5 failed login attempts.",
            },
            {
                "requirement_text": "The system shall lock a user account after 5 failed login attempt.",
                "source_quote": "The system shall export monthly reports as CSV.",
            },
        ],
    )

    replay_run = run_replay(session, live_run.id)

    replayed_requirements = [
        req
        for extracted in session.query(ExtractedRequirement)
        .filter_by(extraction_run_id=replay_run.id)
        .all()
        for req in session.query(Requirement).filter_by(source_extraction_id=extracted.id).all()
    ]
    states = {r.validation_state for r in replayed_requirements}
    assert "fail" in states


# ---------------------------------------------------------------------------
# no live API call
# ---------------------------------------------------------------------------


def test_replay_never_calls_the_extraction_client(session, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    live_run = _make_live_run(session)

    replay_run = run_replay(session, live_run.id)

    assert replay_run.mode == "replay"


# ---------------------------------------------------------------------------
# rejections
# ---------------------------------------------------------------------------


def test_nonexistent_source_run_rejected(session):
    with pytest.raises(ReplaySourceNotFoundError):
        run_replay(session, 999999)


def test_replaying_a_replay_is_rejected(session):
    live_run = _make_live_run(session)
    replay_run = run_replay(session, live_run.id)

    with pytest.raises(ReplaySourceNotLiveError):
        run_replay(session, replay_run.id)


# ---------------------------------------------------------------------------
# boundary conditions
# ---------------------------------------------------------------------------


def test_replaying_an_empty_extraction_produces_no_requirements(session):
    live_run = _make_live_run(session, requirements=[])

    replay_run = run_replay(session, live_run.id)

    copies = (
        session.query(ExtractedRequirement).filter_by(extraction_run_id=replay_run.id).all()
    )
    assert copies == []


def test_same_live_run_can_be_replayed_multiple_times_independently(session):
    live_run = _make_live_run(session)

    first_replay = run_replay(session, live_run.id)
    second_replay = run_replay(session, live_run.id)

    assert first_replay.id != second_replay.id
    first_copies = {
        c.id for c in session.query(ExtractedRequirement).filter_by(extraction_run_id=first_replay.id).all()
    }
    second_copies = {
        c.id for c in session.query(ExtractedRequirement).filter_by(extraction_run_id=second_replay.id).all()
    }
    assert first_copies.isdisjoint(second_copies)
