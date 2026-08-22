from __future__ import annotations

import json

import pytest
from sqlalchemy.orm import Session

from app.db import Base, get_engine
from app.extraction import (
    ExtractionAPIError,
    ExtractionCallResult,
    ExtractionParseError,
    SourceQuoteNotFoundError,
)
from app.extraction.prompt import EXTRACTION_PROMPT_VERSION
from app.extraction_engine import run_extraction
from app.models import (
    ExtractedRequirement,
    ExtractionRun,
    Requirement,
    SourceDocument,
)
from app.seed import seed_validation_rules
from app.validation_engine import run_validation


@pytest.fixture()
def session(tmp_path):
    db_path = tmp_path / "test.db"
    engine = get_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        seed_validation_rules(db_session)
        yield db_session
    engine.dispose()


class FakeExtractionClient:
    def __init__(self, payload, model_name: str = "fake-model-v1", raw_response: str | None = None):
        self.model_name = model_name
        self._text = payload if isinstance(payload, str) else json.dumps(payload)
        self._raw_response = raw_response if raw_response is not None else self._text

    def complete(self, prompt: str) -> ExtractionCallResult:
        return ExtractionCallResult(text=self._text, raw_response=self._raw_response)


class RaisingExtractionClient:
    def __init__(self, model_name: str = "fake-model-v1"):
        self.model_name = model_name

    def complete(self, prompt: str) -> ExtractionCallResult:
        raise ExtractionAPIError("simulated network/API failure")


SOURCE_TEXT = (
    "During the call, ops mentioned the system shall lock a user account "
    "after 5 failed login attempts. Separately, finance asked that the "
    "system shall export monthly reports as CSV."
)


def all_counts(session: Session) -> tuple[int, int, int, int]:
    return (
        session.query(SourceDocument).count(),
        session.query(ExtractionRun).count(),
        session.query(ExtractedRequirement).count(),
        session.query(Requirement).count(),
    )


# ---------------------------------------------------------------------------
# successful extraction
# ---------------------------------------------------------------------------


def test_single_valid_requirement_extracted(session):
    client = FakeExtractionClient(
        {
            "requirements": [
                {
                    "requirement_text": "The system shall lock a user account after 5 failed login attempts.",
                    "source_quote": "the system shall lock a user account after 5 failed login attempts",
                }
            ]
        }
    )

    run = run_extraction(session, client, SOURCE_TEXT)

    assert session.query(ExtractedRequirement).filter_by(extraction_run_id=run.id).count() == 1
    assert session.query(Requirement).count() == 1


def test_multiple_requirements_extracted(session):
    client = FakeExtractionClient(
        {
            "requirements": [
                {
                    "requirement_text": "The system shall lock a user account after 5 failed login attempts.",
                    "source_quote": "the system shall lock a user account after 5 failed login attempts",
                },
                {
                    "requirement_text": "The system shall export monthly reports as CSV.",
                    "source_quote": "the system shall export monthly reports as CSV",
                },
            ]
        }
    )

    run_extraction(session, client, SOURCE_TEXT)

    assert session.query(ExtractedRequirement).count() == 2
    assert session.query(Requirement).count() == 2


def test_empty_extraction_is_a_valid_successful_run(session):
    client = FakeExtractionClient({"requirements": []})

    run = run_extraction(session, client, SOURCE_TEXT)

    assert run.id is not None
    assert session.query(ExtractedRequirement).count() == 0
    assert session.query(Requirement).count() == 0
    assert session.query(SourceDocument).count() == 1


# ---------------------------------------------------------------------------
# source quote / span correctness
# ---------------------------------------------------------------------------


def test_source_quote_stored_exactly(session):
    quote = "the system shall lock a user account after 5 failed login attempts"
    client = FakeExtractionClient(
        {"requirements": [{"requirement_text": "x", "source_quote": quote}]}
    )

    run_extraction(session, client, SOURCE_TEXT)

    extracted = session.query(ExtractedRequirement).one()
    assert extracted.source_quote == quote


def test_source_spans_match_raw_text(session):
    quote = "the system shall lock a user account after 5 failed login attempts"
    client = FakeExtractionClient(
        {"requirements": [{"requirement_text": "x", "source_quote": quote}]}
    )

    run_extraction(session, client, SOURCE_TEXT)

    extracted = session.query(ExtractedRequirement).one()
    assert SOURCE_TEXT[extracted.source_span_start : extracted.source_span_end] == quote
    assert extracted.source_span_start == SOURCE_TEXT.find(quote)


def test_repeated_source_quote_uses_first_occurrence(session):
    text = "shall log errors. Later, shall log errors again in a different context."
    quote = "shall log errors"
    client = FakeExtractionClient(
        {"requirements": [{"requirement_text": "x", "source_quote": quote}]}
    )

    run_extraction(session, client, text)

    extracted = session.query(ExtractedRequirement).one()
    assert extracted.source_span_start == text.find(quote)
    assert extracted.source_span_start == 0


def test_unlocatable_source_quote_fails_and_rolls_back_everything(session):
    client = FakeExtractionClient(
        {
            "requirements": [
                {
                    "requirement_text": "A good one.",
                    "source_quote": "the system shall lock a user account after 5 failed login attempts",
                },
                {
                    "requirement_text": "A bad one.",
                    "source_quote": "this exact phrase does not appear anywhere in the source",
                },
            ]
        }
    )

    with pytest.raises(SourceQuoteNotFoundError):
        run_extraction(session, client, SOURCE_TEXT)

    docs, runs, extracted, requirements = all_counts(session)
    assert docs == 1  # source_documents persists independently
    assert runs == 0
    assert extracted == 0
    assert requirements == 0


# ---------------------------------------------------------------------------
# malformed model output
# ---------------------------------------------------------------------------


def test_malformed_json_fails_and_rolls_back(session):
    client = FakeExtractionClient("not valid json {{{")

    with pytest.raises(ExtractionParseError):
        run_extraction(session, client, SOURCE_TEXT)

    _, runs, extracted, requirements = all_counts(session)
    assert runs == 0
    assert extracted == 0
    assert requirements == 0


def test_non_object_top_level_rejected(session):
    client = FakeExtractionClient("[]")

    with pytest.raises(ExtractionParseError):
        run_extraction(session, client, SOURCE_TEXT)


def test_missing_requirements_key_rejected(session):
    client = FakeExtractionClient({"candidates": []})

    with pytest.raises(ExtractionParseError):
        run_extraction(session, client, SOURCE_TEXT)


def test_requirements_not_a_list_rejected(session):
    client = FakeExtractionClient({"requirements": "not a list"})

    with pytest.raises(ExtractionParseError):
        run_extraction(session, client, SOURCE_TEXT)


def test_malformed_candidate_not_an_object_rejected(session):
    client = FakeExtractionClient({"requirements": ["just a string"]})

    with pytest.raises(ExtractionParseError):
        run_extraction(session, client, SOURCE_TEXT)


def test_missing_requirement_text_rejected(session):
    client = FakeExtractionClient({"requirements": [{"source_quote": "the system shall"}]})

    with pytest.raises(ExtractionParseError):
        run_extraction(session, client, SOURCE_TEXT)


def test_missing_source_quote_rejected(session):
    client = FakeExtractionClient({"requirements": [{"requirement_text": "x"}]})

    with pytest.raises(ExtractionParseError):
        run_extraction(session, client, SOURCE_TEXT)


def test_non_string_field_rejected(session):
    client = FakeExtractionClient({"requirements": [{"requirement_text": 123, "source_quote": "x"}]})

    with pytest.raises(ExtractionParseError):
        run_extraction(session, client, SOURCE_TEXT)


def test_empty_string_field_rejected(session):
    client = FakeExtractionClient({"requirements": [{"requirement_text": "   ", "source_quote": "x"}]})

    with pytest.raises(ExtractionParseError):
        run_extraction(session, client, SOURCE_TEXT)


def test_malformed_output_leaves_no_partial_state(session):
    client = FakeExtractionClient({"requirements": [{"requirement_text": "", "source_quote": ""}]})

    with pytest.raises(ExtractionParseError):
        run_extraction(session, client, SOURCE_TEXT)

    docs, runs, extracted, requirements = all_counts(session)
    assert docs == 1
    assert runs == 0
    assert extracted == 0
    assert requirements == 0


# ---------------------------------------------------------------------------
# API failure
# ---------------------------------------------------------------------------


def test_api_failure_propagates_and_rolls_back(session):
    client = RaisingExtractionClient()

    with pytest.raises(ExtractionAPIError):
        run_extraction(session, client, SOURCE_TEXT)

    docs, runs, extracted, requirements = all_counts(session)
    assert docs == 1  # source document still recorded as submitted
    assert runs == 0
    assert extracted == 0
    assert requirements == 0


# ---------------------------------------------------------------------------
# extraction_runs field correctness
# ---------------------------------------------------------------------------


def test_extraction_run_model_name_recorded(session):
    client = FakeExtractionClient({"requirements": []}, model_name="claude-sonnet-5-test")

    run = run_extraction(session, client, SOURCE_TEXT)

    assert run.model_name == "claude-sonnet-5-test"


def test_extraction_run_prompt_version_recorded(session):
    client = FakeExtractionClient({"requirements": []})

    run = run_extraction(session, client, SOURCE_TEXT)

    assert run.prompt_version == EXTRACTION_PROMPT_VERSION == "1.0.0"


def test_extraction_run_raw_response_recorded(session):
    raw = '{"requirements": []}'
    client = FakeExtractionClient(raw, raw_response=raw)

    run = run_extraction(session, client, SOURCE_TEXT)

    assert run.raw_response == raw


def test_extraction_run_mode_is_live(session):
    client = FakeExtractionClient({"requirements": []})

    run = run_extraction(session, client, SOURCE_TEXT)

    assert run.mode == "live"
    assert run.replayed_from_run_id is None


# ---------------------------------------------------------------------------
# requirement linkage
# ---------------------------------------------------------------------------


def test_requirement_origin_is_ai_generated(session):
    client = FakeExtractionClient(
        {"requirements": [{"requirement_text": "x", "source_quote": "the system shall"}]}
    )

    run_extraction(session, client, SOURCE_TEXT)

    requirement = session.query(Requirement).one()
    assert requirement.origin == "ai_generated"


def test_requirement_source_extraction_id_linkage(session):
    client = FakeExtractionClient(
        {"requirements": [{"requirement_text": "x", "source_quote": "the system shall"}]}
    )

    run_extraction(session, client, SOURCE_TEXT)

    extracted = session.query(ExtractedRequirement).one()
    requirement = session.query(Requirement).one()
    assert requirement.source_extraction_id == extracted.id
    assert requirement.current_text == "x"


# ---------------------------------------------------------------------------
# integration with the existing deterministic validation engine
# ---------------------------------------------------------------------------


def test_extracted_requirement_can_be_validated_by_existing_engine(session):
    client = FakeExtractionClient(
        {
            "requirements": [
                {
                    "requirement_text": "The system shall lock a user account after 5 failed login attempts.",
                    "source_quote": "the system shall lock a user account after 5 failed login attempts",
                }
            ]
        }
    )

    run_extraction(session, client, SOURCE_TEXT)
    requirement = session.query(Requirement).one()

    updated = run_validation(session, requirement.id)

    assert updated.validation_state in ("pass", "warn", "fail")
    assert session.query(Requirement).one().validation_state == updated.validation_state
