from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db_session
from app.api.errors import register_exception_handlers
from app.api.routes.acceptance_criteria import router as acceptance_criteria_router
from app.api.routes.extraction import router as extraction_router
from app.api.routes.requirements import router as requirements_router
from app.db import Base
from app.seed import seed_validation_rules
from app.ui.public_demo_fixture import DEMO_ACKNOWLEDGED_BY, FIXTURE, seed_fixture


def _build_seeded_client() -> TestClient:
    """The exact FastAPI()+in-memory-SQLite+TestClient construction proven
    in Stage 1/Stage 4, seeded with the real captured fixture."""
    fastapi_app = FastAPI()
    register_exception_handlers(fastapi_app)
    fastapi_app.include_router(extraction_router)
    fastapi_app.include_router(requirements_router)
    fastapi_app.include_router(acceptance_criteria_router)

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_factory() as seed_session:
        seed_validation_rules(seed_session)
        seed_fixture(seed_session)

    def override_get_db_session():
        session: Session = session_factory()
        try:
            yield session
        finally:
            session.close()

    fastapi_app.dependency_overrides[get_db_session] = override_get_db_session
    return TestClient(fastapi_app)


def _summary(client: TestClient) -> list[dict]:
    response = client.get("/requirements/summary")
    assert response.status_code == 200
    return response.json()


# ---------------------------------------------------------------------------
# fixture data sanity (no DB involved)
# ---------------------------------------------------------------------------


def test_module_docstring_is_actually_attached():
    # Regression: the module docstring was originally placed after `from
    # __future__ import annotations`, which silently discards it as a dead
    # expression statement instead of attaching it as __doc__ (the same bug
    # class independently found and fixed in streamlit_public_demo.py).
    import app.ui.public_demo_fixture as m

    assert m.__doc__ is not None
    assert "Captured public-demo fixture data" in m.__doc__


def test_fixture_data_has_two_documents_and_three_runs():
    assert len(FIXTURE["source_documents"]) == 2
    assert len(FIXTURE["extraction_runs"]) == 3
    modes = [run["mode"] for run in FIXTURE["extraction_runs"]]
    assert modes.count("live") == 2
    assert modes.count("replay") == 1


def test_fixture_data_contains_no_real_username():
    # The only human-identity-shaped field the fixture data itself could
    # carry is inside acceptance_criteria/requirement dicts, and neither
    # carries a raw username at all (see seed_fixture) - confirmed by
    # scanning every string value in the fixture for the developer's real
    # local OS username never appearing.
    import getpass

    real_username = getpass.getuser()

    def walk(value):
        if isinstance(value, dict):
            return any(walk(v) for v in value.values())
        if isinstance(value, list):
            return any(walk(v) for v in value)
        return isinstance(value, str) and real_username.lower() in value.lower()

    assert not walk(FIXTURE), "fixture data must never contain the capturing developer's OS username"


# ---------------------------------------------------------------------------
# seeding, with no provider key present anywhere
# ---------------------------------------------------------------------------


def test_seed_fixture_works_with_no_provider_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("AI_PROVIDER", raising=False)

    client = _build_seeded_client()
    summary = _summary(client)

    assert len(summary) == 11


def test_seed_fixture_produces_expected_distribution():
    client = _build_seeded_client()
    summary = _summary(client)

    pass_count = sum(1 for r in summary if r["validation_state"] == "pass")
    warn_count = sum(1 for r in summary if r["validation_state"] == "warn")
    fail_count = sum(1 for r in summary if r["validation_state"] == "fail")
    approved = sum(1 for r in summary if r["review_status"] == "approved")
    rejected = sum(1 for r in summary if r["review_status"] == "rejected")
    pending = sum(1 for r in summary if r["review_status"] == "pending")
    acknowledged = sum(1 for r in summary if r["warn_acknowledged"])
    ac_total = sum(r["acceptance_criteria_count"] for r in summary)
    live = sum(1 for r in summary if r["mode"] == "live")
    replay = sum(1 for r in summary if r["mode"] == "replay")
    doc_titles = {r["source_document_title"] for r in summary}

    assert (pass_count, warn_count, fail_count) == (2, 4, 5)
    assert (approved, rejected, pending) == (2, 1, 8)
    assert acknowledged == 1
    assert ac_total == 1
    assert live == 8
    assert replay == 3
    assert doc_titles == {
        "Store manager absence-request process (call notes)",
        "Helpdesk ticket escalation process (stakeholder notes)",
    }


def test_seed_fixture_scrubs_acknowledger_to_neutral_label():
    client = _build_seeded_client()
    summary = _summary(client)

    acknowledged_row = next(r for r in summary if r["warn_acknowledged"])
    review = client.get(f"/requirements/{acknowledged_row['id']}/review").json()

    assert review["requirement"]["warn_acknowledged_by"] == DEMO_ACKNOWLEDGED_BY
    assert review["requirement"]["warn_acknowledged_by"] != os.environ.get("USERNAME")


def test_seed_fixture_acceptance_criterion_matches_capture():
    client = _build_seeded_client()

    review = client.get("/acceptance-criteria/1/review")
    assert review.status_code == 200
    body = review.json()

    assert body["acceptance_criterion"]["validation_state"] == "warn"
    assert body["provenance"]["mode"] == "live"
    assert body["provenance"]["model_name"] == "gemini-3.5-flash"


# ---------------------------------------------------------------------------
# determinism across independent fresh databases
# ---------------------------------------------------------------------------


def test_seed_fixture_is_deterministic_across_two_fresh_databases():
    summary_a = _summary(_build_seeded_client())
    summary_b = _summary(_build_seeded_client())

    # Two wholly independent in-memory databases, seeded from the same
    # static data, starting from the same empty state, must produce
    # byte-for-byte identical summaries - including ids, since both id
    # sequences start fresh at 1.
    assert summary_a == summary_b
