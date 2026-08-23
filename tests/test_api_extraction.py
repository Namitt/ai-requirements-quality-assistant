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

SOURCE_TEXT = (
    "During the call, ops mentioned the system shall lock a user account "
    "after 5 failed login attempts. Separately, finance asked that the "
    "system shall export monthly reports as CSV."
)


class FakeExtractionClient:
    def __init__(self, payload, model_name: str = "fake-model-v1"):
        self.model_name = model_name
        self._text = payload if isinstance(payload, str) else json.dumps(payload)

    def complete(self, prompt: str) -> ExtractionCallResult:
        return ExtractionCallResult(text=self._text, raw_response=self._text)


class RaisingExtractionClient:
    model_name = "fake-model-v1"

    def complete(self, prompt: str):
        from app.extraction import ExtractionAPIError

        raise ExtractionAPIError("simulated network/API failure")


@pytest.fixture()
def client(tmp_path):
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
        yield test_client

    app.dependency_overrides.clear()
    engine.dispose()


def _override_extraction_client(fake_client):
    app.dependency_overrides[get_extraction_client] = lambda: fake_client


# ---------------------------------------------------------------------------
# application health
# ---------------------------------------------------------------------------


def test_application_starts_and_responds(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_reports_unavailable_when_database_has_no_schema(tmp_path):
    # No Base.metadata.create_all() at all - simulates a database that has
    # never been migrated (no tables exist yet).
    db_path = tmp_path / "unmigrated.db"
    engine = get_engine(f"sqlite:///{db_path}")
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db_session():
        session: Session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db_session
    try:
        with TestClient(app, raise_server_exceptions=False) as test_client:
            response = test_client.get("/health")
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    assert response.status_code == 503
    assert "alembic upgrade head" in response.json()["detail"]


def test_health_reports_unavailable_when_validation_rules_catalog_is_empty(tmp_path):
    # Schema exists (tables created) but validation_rules was never
    # seeded - the exact fresh-database gap the seeding migration fixes.
    db_path = tmp_path / "unseeded.db"
    engine = get_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db_session():
        session: Session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db_session
    try:
        with TestClient(app, raise_server_exceptions=False) as test_client:
            response = test_client.get("/health")
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "incomplete" in detail
    assert "DUPLICATE_NEAR" in detail


# ---------------------------------------------------------------------------
# successful extraction
# ---------------------------------------------------------------------------


def test_extraction_endpoint_invokes_engine_and_persists(client):
    _override_extraction_client(
        FakeExtractionClient(
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
    )

    response = client.post("/extractions", json={"raw_text": SOURCE_TEXT, "title": "Call notes"})

    assert response.status_code == 201
    body = response.json()
    assert body["mode"] == "live"
    assert body["replayed_from_run_id"] is None
    assert "raw_response" not in body
    assert len(body["extracted_requirements"]) == 2
    for extracted in body["extracted_requirements"]:
        assert len(extracted["requirements"]) == 1
        assert extracted["requirements"][0]["origin"] == "ai_generated"


def test_extraction_response_source_span_correct(client):
    quote = "the system shall export monthly reports as CSV"
    _override_extraction_client(
        FakeExtractionClient({"requirements": [{"requirement_text": "x", "source_quote": quote}]})
    )

    response = client.post("/extractions", json={"raw_text": SOURCE_TEXT})
    body = response.json()
    extracted = body["extracted_requirements"][0]
    assert extracted["source_quote"] == quote
    assert SOURCE_TEXT[extracted["source_span_start"] : extracted["source_span_end"]] == quote


def test_extracted_requirements_can_be_retrieved(client):
    _override_extraction_client(
        FakeExtractionClient(
            {"requirements": [{"requirement_text": "x", "source_quote": "the system shall lock a user account"}]}
        )
    )

    created = client.post("/extractions", json={"raw_text": SOURCE_TEXT}).json()
    extracted_id = created["extracted_requirements"][0]["id"]

    response = client.get(f"/extracted-requirements/{extracted_id}")
    assert response.status_code == 200
    assert response.json()["id"] == extracted_id


def test_paired_requirements_can_be_retrieved(client):
    _override_extraction_client(
        FakeExtractionClient(
            {"requirements": [{"requirement_text": "x", "source_quote": "the system shall lock a user account"}]}
        )
    )

    created = client.post("/extractions", json={"raw_text": SOURCE_TEXT}).json()
    requirement_id = created["extracted_requirements"][0]["requirements"][0]["id"]

    response = client.get(f"/requirements/{requirement_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == requirement_id
    assert body["origin"] == "ai_generated"
    assert body["validation_state"] == "not_validated"


def test_source_document_can_be_retrieved(client):
    _override_extraction_client(FakeExtractionClient({"requirements": []}))

    created = client.post("/extractions", json={"raw_text": SOURCE_TEXT, "title": "T"}).json()
    doc_id = created["source_document_id"]

    response = client.get(f"/source-documents/{doc_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["raw_text"] == SOURCE_TEXT
    assert body["title"] == "T"


def test_extraction_run_can_be_retrieved(client):
    _override_extraction_client(FakeExtractionClient({"requirements": []}))

    created = client.post("/extractions", json={"raw_text": SOURCE_TEXT}).json()

    response = client.get(f"/extraction-runs/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_empty_extraction_returns_201_with_no_requirements(client):
    _override_extraction_client(FakeExtractionClient({"requirements": []}))

    response = client.post("/extractions", json={"raw_text": SOURCE_TEXT})

    assert response.status_code == 201
    assert response.json()["extracted_requirements"] == []


# ---------------------------------------------------------------------------
# invalid client input
# ---------------------------------------------------------------------------


def test_empty_raw_text_rejected_with_422(client):
    response = client.post("/extractions", json={"raw_text": ""})
    assert response.status_code == 422


def test_missing_raw_text_rejected_with_422(client):
    response = client.post("/extractions", json={})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# domain error mapping
# ---------------------------------------------------------------------------


def test_missing_api_key_returns_502_with_actionable_message(client, monkeypatch):
    # Deliberately does not use _override_extraction_client - this exercises
    # the real get_extraction_client() -> AnthropicExtractionClient() path,
    # proving the fix end-to-end through actual FastAPI dependency
    # resolution, not just the client class in isolation.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    response = client.post("/extractions", json={"raw_text": SOURCE_TEXT})

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "ANTHROPIC_API_KEY" in detail
    assert "traceback" not in detail.lower()


def test_extraction_api_error_mapped_to_502(client):
    _override_extraction_client(RaisingExtractionClient())

    response = client.post("/extractions", json={"raw_text": SOURCE_TEXT})

    assert response.status_code == 502
    assert "detail" in response.json()


def test_malformed_model_output_mapped_to_502(client):
    _override_extraction_client(FakeExtractionClient("not valid json {{{"))

    response = client.post("/extractions", json={"raw_text": SOURCE_TEXT})

    assert response.status_code == 502


def test_unlocatable_source_quote_mapped_to_502(client):
    _override_extraction_client(
        FakeExtractionClient(
            {
                "requirements": [
                    {
                        "requirement_text": "x",
                        "source_quote": "this phrase does not appear anywhere in the source text",
                    }
                ]
            }
        )
    )

    response = client.post("/extractions", json={"raw_text": SOURCE_TEXT})

    assert response.status_code == 502


# ---------------------------------------------------------------------------
# 404s
# ---------------------------------------------------------------------------


def test_missing_source_document_returns_404(client):
    response = client.get("/source-documents/999999")
    assert response.status_code == 404


def test_missing_extraction_run_returns_404(client):
    response = client.get("/extraction-runs/999999")
    assert response.status_code == 404


def test_missing_extracted_requirement_returns_404(client):
    response = client.get("/extracted-requirements/999999")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# listing extraction runs
# ---------------------------------------------------------------------------


def test_list_extraction_runs_returns_all_runs(client):
    _override_extraction_client(FakeExtractionClient({"requirements": []}))
    client.post("/extractions", json={"raw_text": SOURCE_TEXT})
    client.post("/extractions", json={"raw_text": SOURCE_TEXT})

    response = client.get("/extraction-runs")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert all(run["mode"] == "live" for run in body)
    assert all("raw_response" not in run for run in body)


def test_list_extraction_runs_empty_when_none_exist(client):
    response = client.get("/extraction-runs")
    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# replay
# ---------------------------------------------------------------------------


def test_replay_endpoint_creates_replay_run(client):
    _override_extraction_client(
        FakeExtractionClient(
            {
                "requirements": [
                    {
                        "requirement_text": "The system shall lock a user account after 5 failed login attempts.",
                        "source_quote": "the system shall lock a user account after 5 failed login attempts",
                    }
                ]
            }
        )
    )
    live_run = client.post("/extractions", json={"raw_text": SOURCE_TEXT}).json()

    response = client.post(f"/extraction-runs/{live_run['id']}/replay")

    assert response.status_code == 201
    body = response.json()
    assert body["mode"] == "replay"
    assert body["replayed_from_run_id"] == live_run["id"]
    assert "raw_response" not in body
    assert len(body["extracted_requirements"]) == 1
    assert (
        body["extracted_requirements"][0]["requirement_text"]
        == live_run["extracted_requirements"][0]["requirement_text"]
    )


def test_replay_endpoint_does_not_call_extraction_client(client):
    _override_extraction_client(FakeExtractionClient({"requirements": []}))
    live_run = client.post("/extractions", json={"raw_text": SOURCE_TEXT}).json()

    # Swap in a client that raises if it is ever called - replay must never
    # reach the extraction client.
    _override_extraction_client(RaisingExtractionClient())

    response = client.post(f"/extraction-runs/{live_run['id']}/replay")

    assert response.status_code == 201


def test_replay_endpoint_missing_source_run_returns_404(client):
    response = client.post("/extraction-runs/999999/replay")
    assert response.status_code == 404


def test_replay_endpoint_replay_of_replay_returns_409(client):
    _override_extraction_client(FakeExtractionClient({"requirements": []}))
    live_run = client.post("/extractions", json={"raw_text": SOURCE_TEXT}).json()
    replay_run = client.post(f"/extraction-runs/{live_run['id']}/replay").json()

    response = client.post(f"/extraction-runs/{replay_run['id']}/replay")

    assert response.status_code == 409
