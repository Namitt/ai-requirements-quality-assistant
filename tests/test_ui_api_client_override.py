from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db_session
from app.api.errors import register_exception_handlers
from app.api.routes.extraction import router as extraction_router
from app.db import Base
from app.seed import seed_validation_rules
from app.ui import api_client


class _FakeResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _FakeClient:
    """Minimal httpx.Client-compatible stand-in - just enough surface for
    _request() to call .request(method, path, timeout=..., **kwargs) - used
    to test the override mechanism itself in isolation from any real ASGI
    app or network behaviour.
    """

    def __init__(self, payload):
        self._payload = payload
        self.calls: list[tuple[str, str]] = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path))
        return _FakeResponse(200, self._payload)


def _build_real_in_process_app_and_client() -> TestClient:
    """A genuine (not faked) fresh FastAPI() instance wired to a private
    in-memory SQLite database, reusing the real extraction router - the
    same construction proven in the standalone stage-1 proof-of-concept,
    used here to prove api_client's override seam reaches real routes.
    """
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(extraction_router)

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

    def override_get_db_session():
        session: Session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db_session

    return TestClient(app)


# ---------------------------------------------------------------------------
# A. existing behaviour unchanged when no override is active
# ---------------------------------------------------------------------------


def test_no_override_uses_real_http_exactly_as_before(monkeypatch):
    captured = {}

    def fake_httpx_request(method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        return _FakeResponse(200, [{"id": 1, "mode": "live"}])

    monkeypatch.setattr(httpx, "request", fake_httpx_request)

    result = api_client.list_extraction_runs()

    assert result == [{"id": 1, "mode": "live"}]
    assert captured["method"] == "GET"
    assert captured["url"].endswith("/extraction-runs")


# ---------------------------------------------------------------------------
# B. override active -> reaches a REAL FastAPI route via TestClient
# ---------------------------------------------------------------------------


def test_override_reaches_real_route_through_test_client():
    with _build_real_in_process_app_and_client() as test_client:
        with api_client.use_test_client(test_client):
            result = api_client.list_extraction_runs()

    # A real route, real dependency-overridden in-memory DB, real (empty)
    # answer - not a fake payload.
    assert result == []


# ---------------------------------------------------------------------------
# C. override is correctly scoped and does not leak after the block ends
# ---------------------------------------------------------------------------


def test_override_does_not_leak_after_context_exits(monkeypatch):
    fake = _FakeClient(payload={"faked": True})

    with api_client.use_test_client(fake):
        api_client.list_extraction_runs()
    assert fake.calls == [("GET", "/extraction-runs")]

    # Outside the block: must fall back to real HTTP again, not the fake.
    real_http_called = {}

    def fake_httpx_request(method, url, **kwargs):
        real_http_called["hit"] = True
        return _FakeResponse(200, [])

    monkeypatch.setattr(httpx, "request", fake_httpx_request)

    api_client.list_extraction_runs()

    assert real_http_called.get("hit") is True
    assert len(fake.calls) == 1, "fake client received a call after its context had ended"


def test_override_reset_even_when_block_raises():
    fake = _FakeClient(payload={})

    with pytest.raises(RuntimeError):
        with api_client.use_test_client(fake):
            raise RuntimeError("boom")

    # If the ContextVar weren't reset in a `finally`, this would still route
    # through `fake` and silently return {} instead of raising for real HTTP
    # with no server listening.
    with pytest.raises(api_client.APIClientError):
        api_client.list_extraction_runs()


# ---------------------------------------------------------------------------
# D. two independent override contexts never cross
# ---------------------------------------------------------------------------


def test_two_sequential_overrides_never_cross():
    client_a = _FakeClient(payload={"who": "a"})
    client_b = _FakeClient(payload={"who": "b"})

    with api_client.use_test_client(client_a):
        result_a = api_client.list_extraction_runs()
    with api_client.use_test_client(client_b):
        result_b = api_client.list_extraction_runs()

    assert result_a == {"who": "a"}
    assert result_b == {"who": "b"}
    assert len(client_a.calls) == 1
    assert len(client_b.calls) == 1


def test_nested_overrides_restore_the_outer_one_on_exit():
    outer = _FakeClient(payload={"who": "outer"})
    inner = _FakeClient(payload={"who": "inner"})

    with api_client.use_test_client(outer):
        result_before = api_client.list_extraction_runs()

        with api_client.use_test_client(inner):
            result_inner = api_client.list_extraction_runs()

        # Back in the outer scope: must be routed to `outer` again, not
        # left pointing at `inner` and not reset all the way to real HTTP.
        result_after = api_client.list_extraction_runs()

    assert result_before == {"who": "outer"}
    assert result_inner == {"who": "inner"}
    assert result_after == {"who": "outer"}
    assert len(outer.calls) == 2
    assert len(inner.calls) == 1


# ---------------------------------------------------------------------------
# E. disable_ai_drafting() / ai_drafting_disabled() - same ContextVar shape
# as use_test_client() above, for a different purpose (see Stage 6: the
# public demo's Draft Acceptance Criteria control)
# ---------------------------------------------------------------------------


def test_ai_drafting_disabled_defaults_to_false():
    assert api_client.ai_drafting_disabled() is False


def test_ai_drafting_disabled_true_inside_context_and_restored_after():
    assert api_client.ai_drafting_disabled() is False
    with api_client.disable_ai_drafting():
        assert api_client.ai_drafting_disabled() is True
    assert api_client.ai_drafting_disabled() is False


def test_ai_drafting_disabled_reset_even_when_block_raises():
    with pytest.raises(RuntimeError):
        with api_client.disable_ai_drafting():
            assert api_client.ai_drafting_disabled() is True
            raise RuntimeError("boom")
    assert api_client.ai_drafting_disabled() is False
