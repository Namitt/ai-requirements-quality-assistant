from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_db_session, get_extraction_client
from app.db import Base, get_engine
from app.extraction import ExtractionCallResult
from app.main import app
from app.seed import seed_validation_rules

CLEAN_TEXT = "The system shall lock a user account after 5 failed login attempts."
WARN_TEXT = "Reports shall be exportable."
# Near-identical text (differs only by "attempts"/"attempt"), the same
# high-similarity pair used elsewhere in this project to reliably trigger
# DUPLICATE_NEAR's FAIL tier (>=0.90) when both appear in one document.
DUP_TEXT_A = "The system shall lock a user account after 5 failed login attempts."
DUP_TEXT_B = "The system shall lock a user account after 5 failed login attempt."

FULL_VALID_CRITERION = (
    "Given a user with 5 failed login attempts, when they attempt to log in "
    "again, then the system shall lock the account within 2 seconds."
)


class FakeExtractionClient:
    def __init__(self, payload, model_name: str = "fake-model-v1"):
        self.model_name = model_name
        self._text = payload if isinstance(payload, str) else json.dumps(payload)

    def complete(self, prompt: str) -> ExtractionCallResult:
        return ExtractionCallResult(text=self._text, raw_response=self._text)


class FakeAcceptanceCriteriaClient:
    model_name = "fake-ac-model"

    def complete(self, prompt: str) -> ExtractionCallResult:
        text = json.dumps({"criterion_text": FULL_VALID_CRITERION})
        return ExtractionCallResult(text=text, raw_response=text)


def _extraction_payload(*texts: str) -> dict:
    return {"requirements": [{"requirement_text": t, "source_quote": t} for t in texts]}


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


def _extract(
    test_client,
    *texts: str,
    title: str | None = None,
    model_name: str = "fake-model-v1",
) -> dict:
    app.dependency_overrides[get_extraction_client] = lambda: FakeExtractionClient(
        _extraction_payload(*texts), model_name=model_name
    )
    raw_text = " ".join(texts)
    response = test_client.post(
        "/extractions", json={"raw_text": raw_text, "title": title}
    )
    return response.json()


def _requirement_ids(extraction_run: dict) -> list[int]:
    return [
        req["id"]
        for extracted in extraction_run["extracted_requirements"]
        for req in extracted["requirements"]
    ]


def _summary_by_id(test_client) -> dict[int, dict]:
    response = test_client.get("/requirements/summary")
    assert response.status_code == 200
    return {row["id"]: row for row in response.json()}


# ---------------------------------------------------------------------------
# empty dataset / route registration
# ---------------------------------------------------------------------------


def test_summary_empty_dataset_returns_empty_list(client):
    response = client.get("/requirements/summary")

    assert response.status_code == 200
    assert response.json() == []


def test_summary_endpoint_not_shadowed_by_requirement_id_route(client):
    run = _extract(client, CLEAN_TEXT)
    assert _requirement_ids(run)

    response = client.get("/requirements/summary")

    # A regression guard: /requirements/summary must be routed to this
    # endpoint, not swallowed by GET /requirements/{requirement_id} (which
    # would instead return 422 trying to coerce "summary" to int).
    assert response.status_code == 200
    assert isinstance(response.json(), list)


# ---------------------------------------------------------------------------
# multiple requirements / provenance
# ---------------------------------------------------------------------------


def test_summary_returns_multiple_requirements(client):
    run = _extract(client, CLEAN_TEXT)
    other_run = _extract(client, WARN_TEXT, title="Second doc")
    expected_ids = set(_requirement_ids(run)) | set(_requirement_ids(other_run))

    summary = _summary_by_id(client)

    assert expected_ids <= summary.keys()


def test_summary_represents_model_and_mode_for_live_run(client):
    run = _extract(client, CLEAN_TEXT, model_name="gemini-3.5-flash")
    requirement_id = _requirement_ids(run)[0]

    row = _summary_by_id(client)[requirement_id]

    assert row["model_name"] == "gemini-3.5-flash"
    assert row["mode"] == "live"


def test_summary_represents_model_and_mode_for_replayed_run(client):
    run = _extract(client, CLEAN_TEXT, model_name="gemini-3.5-flash")
    replay = client.post(f"/extraction-runs/{run['id']}/replay").json()
    replayed_requirement_id = _requirement_ids(replay)[0]

    row = _summary_by_id(client)[replayed_requirement_id]

    assert row["model_name"] == "gemini-3.5-flash"
    assert row["mode"] == "replay"


# ---------------------------------------------------------------------------
# validation state / review status / WARN acknowledgement
# ---------------------------------------------------------------------------


def test_summary_represents_validation_state_pass_warn_fail(client):
    pass_run = _extract(client, CLEAN_TEXT, title="pass doc")
    pass_id = _requirement_ids(pass_run)[0]
    client.post(f"/requirements/{pass_id}/validate")

    warn_run = _extract(client, WARN_TEXT, title="warn doc")
    warn_id = _requirement_ids(warn_run)[0]
    client.post(f"/requirements/{warn_id}/validate")

    dup_run = _extract(client, DUP_TEXT_A, DUP_TEXT_B, title="dup doc")
    dup_ids = _requirement_ids(dup_run)
    for rid in dup_ids:
        client.post(f"/requirements/{rid}/validate")
    fail_id = dup_ids[1]

    summary = _summary_by_id(client)

    assert summary[pass_id]["validation_state"] == "pass"
    assert summary[warn_id]["validation_state"] == "warn"
    assert summary[fail_id]["validation_state"] == "fail"


def test_summary_represents_review_status(client):
    approved_run = _extract(client, CLEAN_TEXT, title="approved doc")
    approved_id = _requirement_ids(approved_run)[0]
    client.post(f"/requirements/{approved_id}/validate")
    client.post(f"/requirements/{approved_id}/approve")

    rejected_run = _extract(client, CLEAN_TEXT, title="rejected doc")
    rejected_id = _requirement_ids(rejected_run)[0]
    client.post(f"/requirements/{rejected_id}/reject")

    pending_run = _extract(client, CLEAN_TEXT, title="pending doc")
    pending_id = _requirement_ids(pending_run)[0]

    summary = _summary_by_id(client)

    assert summary[approved_id]["review_status"] == "approved"
    assert summary[rejected_id]["review_status"] == "rejected"
    assert summary[pending_id]["review_status"] == "pending"


def test_summary_represents_warn_acknowledgement(client):
    acked_run = _extract(client, WARN_TEXT, title="acked doc")
    acked_id = _requirement_ids(acked_run)[0]
    client.post(f"/requirements/{acked_id}/validate")
    client.post(
        f"/requirements/{acked_id}/approve", json={"acknowledge_warning": True}
    )

    unacked_run = _extract(client, WARN_TEXT, title="unacked doc")
    unacked_id = _requirement_ids(unacked_run)[0]
    client.post(f"/requirements/{unacked_id}/validate")

    summary = _summary_by_id(client)

    assert summary[acked_id]["warn_acknowledged"] is True
    assert summary[unacked_id]["warn_acknowledged"] is False


# ---------------------------------------------------------------------------
# acceptance-criteria count
# ---------------------------------------------------------------------------


def test_summary_represents_acceptance_criteria_count(client):
    with_ac_run = _extract(client, CLEAN_TEXT, title="with ac doc")
    with_ac_id = _requirement_ids(with_ac_run)[0]
    app.dependency_overrides[get_extraction_client] = lambda: FakeAcceptanceCriteriaClient()
    draft_response = client.post(f"/requirements/{with_ac_id}/acceptance-criteria")
    assert draft_response.status_code == 201

    without_ac_run = _extract(client, CLEAN_TEXT, title="no ac doc")
    without_ac_id = _requirement_ids(without_ac_run)[0]

    summary = _summary_by_id(client)

    assert summary[with_ac_id]["acceptance_criteria_count"] == 1
    assert summary[without_ac_id]["acceptance_criteria_count"] == 0


# ---------------------------------------------------------------------------
# multiple documents / extraction runs
# ---------------------------------------------------------------------------


def test_summary_represents_requirements_from_different_documents(client):
    run_a = _extract(client, CLEAN_TEXT, title="Document A")
    run_b = _extract(client, WARN_TEXT, title="Document B")
    id_a = _requirement_ids(run_a)[0]
    id_b = _requirement_ids(run_b)[0]

    summary = _summary_by_id(client)

    assert summary[id_a]["source_document_title"] == "Document A"
    assert summary[id_b]["source_document_title"] == "Document B"
    assert summary[id_a]["source_document_id"] != summary[id_b]["source_document_id"]
