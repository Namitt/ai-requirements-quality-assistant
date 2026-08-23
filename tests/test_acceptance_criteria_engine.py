from __future__ import annotations

import json

import pytest
from sqlalchemy.orm import Session

from app.acceptance_criteria_engine import (
    AcceptanceCriteriaReplaySourceNotFoundError,
    AcceptanceCriteriaReplaySourceNotLiveError,
    draft_acceptance_criteria,
    replay_acceptance_criteria,
)
from app.acceptance_criteria.prompt import ACCEPTANCE_CRITERIA_PROMPT_VERSION
from app.db import Base, get_engine
from app.extraction import ExtractionCallResult
from app.models import AcceptanceCriterion, ExtractedAcceptanceCriterion, Requirement, ValidationRun
from app.seed import seed_validation_rules

CRITERION_TEXT = (
    "Given a user with 5 failed login attempts, when they attempt to log in "
    "again, then the system shall lock the account within 2 seconds."
)


class FakeExtractionClient:
    def __init__(self, criterion_text: str = CRITERION_TEXT, model_name: str = "fake-ac-model"):
        self.model_name = model_name
        self._text = json.dumps({"criterion_text": criterion_text})

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


def make_requirement(session: Session, review_status: str = "pending") -> Requirement:
    requirement = Requirement(
        current_text="The system shall lock a user account after 5 failed login attempts.",
        origin="ai_generated",
        review_status=review_status,
    )
    if review_status == "approved":
        requirement.validation_state = "pass"
    session.add(requirement)
    session.commit()
    return requirement


# ---------------------------------------------------------------------------
# live drafting
# ---------------------------------------------------------------------------


def test_draft_creates_extracted_and_mutable_rows(session):
    requirement = make_requirement(session)

    criterion = draft_acceptance_criteria(session, FakeExtractionClient(), requirement.id)

    assert criterion.id is not None
    extracted = session.get(ExtractedAcceptanceCriterion, criterion.source_extraction_id)
    assert extracted is not None
    assert extracted.criterion_text == CRITERION_TEXT
    assert criterion.current_text == CRITERION_TEXT


def test_draft_sets_mode_live(session):
    requirement = make_requirement(session)

    criterion = draft_acceptance_criteria(session, FakeExtractionClient(), requirement.id)

    extracted = session.get(ExtractedAcceptanceCriterion, criterion.source_extraction_id)
    assert extracted.mode == "live"
    assert extracted.replayed_from_id is None


def test_draft_records_model_and_prompt_version(session):
    requirement = make_requirement(session)

    criterion = draft_acceptance_criteria(
        session, FakeExtractionClient(model_name="claude-sonnet-5-test"), requirement.id
    )

    extracted = session.get(ExtractedAcceptanceCriterion, criterion.source_extraction_id)
    assert extracted.model_name == "claude-sonnet-5-test"
    assert extracted.prompt_version == ACCEPTANCE_CRITERIA_PROMPT_VERSION


def test_draft_requirement_id_recorded_on_extracted_row(session):
    requirement = make_requirement(session)

    criterion = draft_acceptance_criteria(session, FakeExtractionClient(), requirement.id)

    extracted = session.get(ExtractedAcceptanceCriterion, criterion.source_extraction_id)
    assert extracted.requirement_id == requirement.id


@pytest.mark.parametrize("review_status", ["pending", "approved", "rejected"])
def test_draft_works_regardless_of_parent_review_status(session, review_status):
    requirement = make_requirement(session, review_status=review_status)

    criterion = draft_acceptance_criteria(session, FakeExtractionClient(), requirement.id)

    assert criterion.id is not None


def test_draft_never_changes_parent_requirement_review_status(session):
    for status in ("pending", "approved", "rejected"):
        requirement = make_requirement(session, review_status=status)
        draft_acceptance_criteria(session, FakeExtractionClient(), requirement.id)
        session.refresh(requirement)
        assert requirement.review_status == status


def test_draft_never_auto_approves_the_criterion(session):
    requirement = make_requirement(session)

    criterion = draft_acceptance_criteria(session, FakeExtractionClient(), requirement.id)

    assert criterion.review_status == "pending"


def test_draft_automatically_runs_validation(session):
    requirement = make_requirement(session)

    criterion = draft_acceptance_criteria(session, FakeExtractionClient(), requirement.id)

    assert criterion.validation_state in ("pass", "warn", "fail")
    run_count = (
        session.query(ValidationRun).filter_by(acceptance_criterion_id=criterion.id).count()
    )
    assert run_count == 1


def test_draft_rejects_nonexistent_requirement(session):
    with pytest.raises(ValueError):
        draft_acceptance_criteria(session, FakeExtractionClient(), 999999)


# ---------------------------------------------------------------------------
# replay
# ---------------------------------------------------------------------------


def test_replay_creates_new_extracted_and_mutable_rows(session):
    requirement = make_requirement(session)
    live = draft_acceptance_criteria(session, FakeExtractionClient(), requirement.id)

    replay = replay_acceptance_criteria(session, live.source_extraction_id)

    assert replay.id != live.id
    assert replay.source_extraction_id != live.source_extraction_id


def test_replay_sets_mode_replay_and_replayed_from_id(session):
    requirement = make_requirement(session)
    live = draft_acceptance_criteria(session, FakeExtractionClient(), requirement.id)

    replay = replay_acceptance_criteria(session, live.source_extraction_id)

    replay_extracted = session.get(ExtractedAcceptanceCriterion, replay.source_extraction_id)
    assert replay_extracted.mode == "replay"
    assert replay_extracted.replayed_from_id == live.source_extraction_id


def test_replay_copies_metadata_exactly(session):
    requirement = make_requirement(session)
    live = draft_acceptance_criteria(
        session, FakeExtractionClient(model_name="claude-sonnet-5-test"), requirement.id
    )
    live_extracted = session.get(ExtractedAcceptanceCriterion, live.source_extraction_id)

    replay = replay_acceptance_criteria(session, live.source_extraction_id)
    replay_extracted = session.get(ExtractedAcceptanceCriterion, replay.source_extraction_id)

    assert replay_extracted.criterion_text == live_extracted.criterion_text
    assert replay_extracted.model_name == live_extracted.model_name
    assert replay_extracted.prompt_version == live_extracted.prompt_version
    assert replay_extracted.requirement_id == live_extracted.requirement_id


def test_replay_produces_fresh_ids(session):
    requirement = make_requirement(session)
    live = draft_acceptance_criteria(session, FakeExtractionClient(), requirement.id)

    replay = replay_acceptance_criteria(session, live.source_extraction_id)

    assert replay.id != live.id
    assert replay.source_extraction_id != live.source_extraction_id


def test_replay_never_calls_the_extraction_client(session, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    requirement = make_requirement(session)
    live = draft_acceptance_criteria(session, FakeExtractionClient(), requirement.id)

    replay = replay_acceptance_criteria(session, live.source_extraction_id)

    assert replay.id is not None


def test_replay_never_modifies_original_live_row(session):
    requirement = make_requirement(session)
    live = draft_acceptance_criteria(session, FakeExtractionClient(), requirement.id)
    original_text = session.get(
        ExtractedAcceptanceCriterion, live.source_extraction_id
    ).criterion_text

    replay_acceptance_criteria(session, live.source_extraction_id)

    live_extracted = session.get(ExtractedAcceptanceCriterion, live.source_extraction_id)
    assert live_extracted.mode == "live"
    assert live_extracted.criterion_text == original_text


def test_replay_automatically_runs_validation(session):
    requirement = make_requirement(session)
    live = draft_acceptance_criteria(session, FakeExtractionClient(), requirement.id)

    replay = replay_acceptance_criteria(session, live.source_extraction_id)

    assert replay.validation_state in ("pass", "warn", "fail")
    run_count = (
        session.query(ValidationRun).filter_by(acceptance_criterion_id=replay.id).count()
    )
    assert run_count == 1


def test_replay_of_replay_rejected(session):
    requirement = make_requirement(session)
    live = draft_acceptance_criteria(session, FakeExtractionClient(), requirement.id)
    replay = replay_acceptance_criteria(session, live.source_extraction_id)

    with pytest.raises(AcceptanceCriteriaReplaySourceNotLiveError):
        replay_acceptance_criteria(session, replay.source_extraction_id)


def test_replay_missing_source_rejected(session):
    with pytest.raises(AcceptanceCriteriaReplaySourceNotFoundError):
        replay_acceptance_criteria(session, 999999)
