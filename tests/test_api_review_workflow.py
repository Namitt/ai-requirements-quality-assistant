from __future__ import annotations

import getpass
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_db_session, get_extraction_client
from app.db import Base, get_engine
from app.extraction import ExtractionCallResult
from app.main import app
from app.models import Requirement, RequirementEdit, ValidationRun
from app.seed import seed_validation_rules

SOURCE_TEXT = "The system shall lock a user account after 5 failed login attempts."

# A requirement extracted verbatim from SOURCE_TEXT will trigger AMBIGUOUS_WORDING?
# No - checked against validation-rules.md: this exact sentence has a measurable
# condition, no ambiguous terms, and an actor ("the system"), so it validates
# clean -> PASS overall, with no siblings to compare against -> DUPLICATE_NEAR
# and POSSIBLE_CONTRADICTION both PASS too.
CLEAN_TEXT = "The system shall lock a user account after 5 failed login attempts."

# Deliberately triggers MISSING_ACCEPTANCE_CONDITION and MISSING_ACTOR -> WARN.
WARN_TEXT = "Reports shall be exportable."


class FakeExtractionClient:
    def __init__(self, payload, model_name: str = "fake-model-v1"):
        self.model_name = model_name
        self._text = payload if isinstance(payload, str) else json.dumps(payload)

    def complete(self, prompt: str) -> ExtractionCallResult:
        return ExtractionCallResult(text=self._text, raw_response=self._text)


def _extraction_payload(text: str) -> dict:
    return {"requirements": [{"requirement_text": text, "source_quote": text}]}


@pytest.fixture()
def client_and_sessionmaker(tmp_path):
    db_path = tmp_path / "test.db"
    engine = get_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_factory() as seed_session:
        seed_validation_rules(seed_session)

    def override_get_db_session():
        session: Session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db_session

    with TestClient(app) as test_client:
        yield test_client, session_factory

    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture()
def client(client_and_sessionmaker):
    test_client, _ = client_and_sessionmaker
    return test_client


def _extract_and_validate(test_client, text: str = CLEAN_TEXT) -> int:
    app.dependency_overrides[get_extraction_client] = lambda: FakeExtractionClient(
        _extraction_payload(text)
    )
    created = test_client.post("/extractions", json={"raw_text": text}).json()
    requirement_id = created["extracted_requirements"][0]["requirements"][0]["id"]
    test_client.post(f"/requirements/{requirement_id}/validate")
    return requirement_id


def _make_warn_requirement(test_client) -> int:
    return _extract_and_validate(test_client, WARN_TEXT)


def _make_pass_requirement(test_client) -> int:
    return _extract_and_validate(test_client, CLEAN_TEXT)


def _make_unvalidated_requirement(test_client, text: str = CLEAN_TEXT) -> int:
    app.dependency_overrides[get_extraction_client] = lambda: FakeExtractionClient(
        _extraction_payload(text)
    )
    created = test_client.post("/extractions", json={"raw_text": text}).json()
    return created["extracted_requirements"][0]["requirements"][0]["id"]


def _make_duplicate_pair(test_client) -> tuple[int, int]:
    # Near-identical text (differs only by "attempts"/"attempt"), empirically
    # verified elsewhere in this project to score ~0.99 similarity under
    # DUPLICATE_NEAR - well into its FAIL tier (>=0.90). Both candidates must
    # come from the SAME extraction (same source_document) since DUPLICATE_NEAR
    # only compares requirements within the same document.
    text_a = "The system shall lock a user account after 5 failed login attempts."
    text_b = "The system shall lock a user account after 5 failed login attempt."
    raw_text = f"{text_a} {text_b}"
    app.dependency_overrides[get_extraction_client] = lambda: FakeExtractionClient(
        {
            "requirements": [
                {"requirement_text": text_a, "source_quote": text_a},
                {"requirement_text": text_b, "source_quote": text_b},
            ]
        }
    )
    created = test_client.post("/extractions", json={"raw_text": raw_text}).json()
    req_ids = [
        extracted["requirements"][0]["id"] for extracted in created["extracted_requirements"]
    ]
    for req_id in req_ids:
        test_client.post(f"/requirements/{req_id}/validate")
    return req_ids[0], req_ids[1]


# ---------------------------------------------------------------------------
# PATCH
# ---------------------------------------------------------------------------


def test_edit_pending_requirement_succeeds(client):
    requirement_id = _make_pass_requirement(client)

    response = client.patch(
        f"/requirements/{requirement_id}", json={"current_text": "The system shall do X."}
    )

    assert response.status_code == 200
    assert response.json()["current_text"] == "The system shall do X."


def test_edit_creates_requirement_edit_row(client_and_sessionmaker):
    test_client, session_factory = client_and_sessionmaker
    requirement_id = _make_pass_requirement(test_client)

    test_client.patch(f"/requirements/{requirement_id}", json={"current_text": "New text."})

    with session_factory() as s:
        edits = s.query(RequirementEdit).filter_by(requirement_id=requirement_id).all()
    assert len(edits) == 1


def test_edit_previous_and_new_text_correct(client_and_sessionmaker):
    test_client, session_factory = client_and_sessionmaker
    requirement_id = _make_pass_requirement(test_client)

    test_client.patch(f"/requirements/{requirement_id}", json={"current_text": "New text."})

    with session_factory() as s:
        edit = s.query(RequirementEdit).filter_by(requirement_id=requirement_id).one()
    assert edit.previous_text == CLEAN_TEXT
    assert edit.new_text == "New text."


def test_edit_edited_by_uses_getuser_convention(client_and_sessionmaker):
    test_client, session_factory = client_and_sessionmaker
    requirement_id = _make_pass_requirement(test_client)

    test_client.patch(f"/requirements/{requirement_id}", json={"current_text": "New text."})

    with session_factory() as s:
        edit = s.query(RequirementEdit).filter_by(requirement_id=requirement_id).one()
    assert edit.edited_by == getpass.getuser()


def test_edit_triggers_new_validation_run(client_and_sessionmaker):
    test_client, session_factory = client_and_sessionmaker
    requirement_id = _make_pass_requirement(test_client)

    with session_factory() as s:
        runs_before = s.query(ValidationRun).filter_by(requirement_id=requirement_id).count()

    test_client.patch(f"/requirements/{requirement_id}", json={"current_text": "New text."})

    with session_factory() as s:
        runs_after = s.query(ValidationRun).filter_by(requirement_id=requirement_id).count()
    assert runs_after == runs_before + 1


def test_edit_preserves_historical_validation_run(client_and_sessionmaker):
    test_client, session_factory = client_and_sessionmaker
    requirement_id = _make_pass_requirement(test_client)

    with session_factory() as s:
        first_run_id = (
            s.query(ValidationRun).filter_by(requirement_id=requirement_id).one().id
        )

    test_client.patch(f"/requirements/{requirement_id}", json={"current_text": "New text."})

    with session_factory() as s:
        run_ids = {
            r.id for r in s.query(ValidationRun).filter_by(requirement_id=requirement_id).all()
        }
    assert first_run_id in run_ids
    assert len(run_ids) == 2


def test_edit_latest_validation_state_reflects_edit(client):
    requirement_id = _make_pass_requirement(client)

    response = client.patch(
        f"/requirements/{requirement_id}", json={"current_text": "Reports shall be exportable."}
    )

    assert response.json()["validation_state"] == "warn"


def test_approved_requirement_cannot_be_edited(client):
    requirement_id = _make_pass_requirement(client)
    client.post(f"/requirements/{requirement_id}/approve")

    response = client.patch(f"/requirements/{requirement_id}", json={"current_text": "x"})

    assert response.status_code == 409


def test_rejected_requirement_cannot_be_edited(client):
    requirement_id = _make_pass_requirement(client)
    client.post(f"/requirements/{requirement_id}/reject")

    response = client.patch(f"/requirements/{requirement_id}", json={"current_text": "x"})

    assert response.status_code == 409


def test_validation_failure_during_edit_leaves_no_partial_state(client_and_sessionmaker):
    test_client, session_factory = client_and_sessionmaker
    requirement_id = _make_pass_requirement(test_client)

    with session_factory() as s:
        edits_before = s.query(RequirementEdit).filter_by(requirement_id=requirement_id).count()
        runs_before = s.query(ValidationRun).filter_by(requirement_id=requirement_id).count()

    no_raise_client = TestClient(app, raise_server_exceptions=False)
    with patch(
        "app.validation_engine.ambiguous_wording.evaluate", side_effect=RuntimeError("boom")
    ):
        response = no_raise_client.patch(
            f"/requirements/{requirement_id}", json={"current_text": "New text."}
        )

    assert response.status_code == 500

    with session_factory() as s:
        edits_after = s.query(RequirementEdit).filter_by(requirement_id=requirement_id).count()
        runs_after = s.query(ValidationRun).filter_by(requirement_id=requirement_id).count()
        requirement = s.get(Requirement, requirement_id)

    assert edits_after == edits_before
    assert runs_after == runs_before
    assert requirement.current_text == CLEAN_TEXT


def test_edit_empty_text_rejected(client):
    requirement_id = _make_pass_requirement(client)

    response = client.patch(f"/requirements/{requirement_id}", json={"current_text": ""})

    assert response.status_code == 422


def test_edit_missing_requirement_returns_404(client):
    response = client.patch("/requirements/999999", json={"current_text": "x"})
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# APPROVE
# ---------------------------------------------------------------------------


def test_pass_requirement_can_be_approved(client):
    requirement_id = _make_pass_requirement(client)

    response = client.post(f"/requirements/{requirement_id}/approve")

    assert response.status_code == 200
    assert response.json()["review_status"] == "approved"


def test_warn_requirement_cannot_be_approved_without_acknowledgement(client):
    requirement_id = _make_warn_requirement(client)

    response = client.post(f"/requirements/{requirement_id}/approve")

    assert response.status_code == 409


def test_warn_requirement_approved_with_explicit_acknowledgement(client):
    requirement_id = _make_warn_requirement(client)

    response = client.post(
        f"/requirements/{requirement_id}/approve", json={"acknowledge_warning": True}
    )

    assert response.status_code == 200
    assert response.json()["review_status"] == "approved"


def test_warn_acknowledgement_fields_populated(client_and_sessionmaker):
    test_client, session_factory = client_and_sessionmaker
    requirement_id = _make_warn_requirement(test_client)

    test_client.post(f"/requirements/{requirement_id}/approve", json={"acknowledge_warning": True})

    with session_factory() as s:
        requirement = s.get(Requirement, requirement_id)
    assert requirement.warn_acknowledged_at is not None
    assert requirement.warn_acknowledged_by == getpass.getuser()


def test_fail_requirement_cannot_be_approved(client):
    _first_id, second_id = _make_duplicate_pair(client)

    response = client.post(f"/requirements/{second_id}/approve")

    assert response.status_code == 409


def test_failed_approval_does_not_change_review_status(client_and_sessionmaker):
    test_client, session_factory = client_and_sessionmaker
    _first_id, dup_id = _make_duplicate_pair(test_client)

    test_client.post(f"/requirements/{dup_id}/approve")

    with session_factory() as s:
        requirement = s.get(Requirement, dup_id)
    assert requirement.review_status == "pending"


def test_approval_does_not_create_new_validation_run(client_and_sessionmaker):
    test_client, session_factory = client_and_sessionmaker
    requirement_id = _make_pass_requirement(test_client)

    with session_factory() as s:
        runs_before = s.query(ValidationRun).filter_by(requirement_id=requirement_id).count()

    test_client.post(f"/requirements/{requirement_id}/approve")

    with session_factory() as s:
        runs_after = s.query(ValidationRun).filter_by(requirement_id=requirement_id).count()
    assert runs_after == runs_before


def test_approval_preserves_validation_history(client_and_sessionmaker):
    test_client, session_factory = client_and_sessionmaker
    requirement_id = _make_warn_requirement(test_client)

    test_client.post(f"/requirements/{requirement_id}/approve", json={"acknowledge_warning": True})

    with session_factory() as s:
        count = s.query(ValidationRun).filter_by(requirement_id=requirement_id).count()
    assert count == 1


def test_approve_missing_requirement_returns_404(client):
    response = client.post("/requirements/999999/approve")
    assert response.status_code == 404


def test_not_validated_requirement_cannot_be_approved(client):
    requirement_id = _make_unvalidated_requirement(client)

    response = client.post(f"/requirements/{requirement_id}/approve")

    assert response.status_code == 409


def test_rejected_requirement_cannot_be_approved(client):
    requirement_id = _make_pass_requirement(client)
    client.post(f"/requirements/{requirement_id}/reject")

    response = client.post(f"/requirements/{requirement_id}/approve")

    assert response.status_code == 409


# ---------------------------------------------------------------------------
# REJECT
# ---------------------------------------------------------------------------


def test_pending_requirement_can_be_rejected(client):
    requirement_id = _make_pass_requirement(client)

    response = client.post(f"/requirements/{requirement_id}/reject")

    assert response.status_code == 200
    assert response.json()["review_status"] == "rejected"


def test_warn_requirement_rejected_without_acknowledgement(client):
    requirement_id = _make_warn_requirement(client)

    response = client.post(f"/requirements/{requirement_id}/reject")

    assert response.status_code == 200
    assert response.json()["review_status"] == "rejected"


def test_fail_requirement_can_be_rejected(client):
    _first_id, dup_id = _make_duplicate_pair(client)

    response = client.post(f"/requirements/{dup_id}/reject")

    assert response.status_code == 200
    assert response.json()["review_status"] == "rejected"


def test_rejection_does_not_delete_requirement(client_and_sessionmaker):
    test_client, session_factory = client_and_sessionmaker
    requirement_id = _make_pass_requirement(test_client)

    test_client.post(f"/requirements/{requirement_id}/reject")

    with session_factory() as s:
        requirement = s.get(Requirement, requirement_id)
    assert requirement is not None


def test_rejection_preserves_validation_history(client_and_sessionmaker):
    test_client, session_factory = client_and_sessionmaker
    requirement_id = _make_pass_requirement(test_client)

    test_client.post(f"/requirements/{requirement_id}/reject")

    with session_factory() as s:
        count = s.query(ValidationRun).filter_by(requirement_id=requirement_id).count()
    assert count == 1


def test_rejection_preserves_extracted_evidence(client):
    requirement_id = _make_pass_requirement(client)

    client.post(f"/requirements/{requirement_id}/reject")

    response = client.get(f"/requirements/{requirement_id}/review")
    assert response.json()["extracted_evidence"] is not None


def test_reject_missing_requirement_returns_404(client):
    response = client.post("/requirements/999999/reject")
    assert response.status_code == 404


def test_approved_requirement_cannot_be_rejected(client):
    requirement_id = _make_pass_requirement(client)
    client.post(f"/requirements/{requirement_id}/approve")

    response = client.post(f"/requirements/{requirement_id}/reject")

    assert response.status_code == 409


# ---------------------------------------------------------------------------
# REVIEW
# ---------------------------------------------------------------------------


def test_review_returns_requirement_details(client):
    requirement_id = _make_pass_requirement(client)

    response = client.get(f"/requirements/{requirement_id}/review")

    assert response.status_code == 200
    assert response.json()["requirement"]["id"] == requirement_id


def test_review_returns_extracted_evidence(client):
    requirement_id = _make_pass_requirement(client)

    response = client.get(f"/requirements/{requirement_id}/review")

    evidence = response.json()["extracted_evidence"]
    assert evidence["source_quote"] == CLEAN_TEXT
    assert evidence["source_document_id"] is not None


def test_review_returns_latest_validation_results(client):
    requirement_id = _make_pass_requirement(client)

    response = client.get(f"/requirements/{requirement_id}/review")

    validation = response.json()["latest_validation"]
    assert validation is not None
    assert len(validation["results"]) == 5
    codes = {r["rule_code"] for r in validation["results"]}
    assert "DUPLICATE_NEAR" in codes


def test_review_returns_edit_history_in_order(client):
    requirement_id = _make_pass_requirement(client)
    client.patch(f"/requirements/{requirement_id}", json={"current_text": "First edit."})
    client.patch(f"/requirements/{requirement_id}", json={"current_text": "Second edit."})

    response = client.get(f"/requirements/{requirement_id}/review")

    history = response.json()["edit_history"]
    assert len(history) == 2
    assert history[0]["new_text"] == "First edit."
    assert history[1]["new_text"] == "Second edit."


def test_review_does_not_expose_raw_response(client):
    requirement_id = _make_pass_requirement(client)

    response = client.get(f"/requirements/{requirement_id}/review")

    assert "raw_response" not in json.dumps(response.json())


def test_review_missing_requirement_returns_404(client):
    response = client.get("/requirements/999999/review")
    assert response.status_code == 404
