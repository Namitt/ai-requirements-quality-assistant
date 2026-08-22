from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_db_session, get_extraction_client
from app.db import Base, get_engine
from app.extraction import ExtractionCallResult
from app.main import app
from app.models import Requirement, ValidationRule
from app.seed import seed_validation_rules

SOURCE_TEXT = (
    "The system shall lock a user account after 5 failed login attempts."
)


class FakeExtractionClient:
    def __init__(self, payload, model_name: str = "fake-model-v1"):
        self.model_name = model_name
        self._text = payload if isinstance(payload, str) else json.dumps(payload)

    def complete(self, prompt: str) -> ExtractionCallResult:
        return ExtractionCallResult(text=self._text, raw_response=self._text)


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
    app.dependency_overrides[get_extraction_client] = lambda: FakeExtractionClient(
        {
            "requirements": [
                {
                    "requirement_text": "The system shall lock a user account after 5 failed login attempts.",
                    "source_quote": "The system shall lock a user account after 5 failed login attempts.",
                }
            ]
        }
    )

    with TestClient(app) as test_client:
        yield test_client, session_factory

    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture()
def client(client_and_sessionmaker):
    test_client, _ = client_and_sessionmaker
    return test_client


def _create_requirement_via_extraction(test_client) -> int:
    response = test_client.post("/extractions", json={"raw_text": SOURCE_TEXT})
    return response.json()["extracted_requirements"][0]["requirements"][0]["id"]


# ---------------------------------------------------------------------------
# listing / retrieval
# ---------------------------------------------------------------------------


def test_list_requirements_returns_created_requirement(client):
    requirement_id = _create_requirement_via_extraction(client)

    response = client.get("/requirements")

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()]
    assert requirement_id in ids


def test_get_requirement_by_id(client):
    requirement_id = _create_requirement_via_extraction(client)

    response = client.get(f"/requirements/{requirement_id}")

    assert response.status_code == 200
    assert response.json()["id"] == requirement_id


def test_missing_requirement_returns_404(client):
    response = client.get("/requirements/999999")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# validation trigger
# ---------------------------------------------------------------------------


def test_validate_requirement_via_api(client):
    requirement_id = _create_requirement_via_extraction(client)

    response = client.post(f"/requirements/{requirement_id}/validate")

    assert response.status_code == 200
    body = response.json()
    assert body["requirement"]["id"] == requirement_id
    assert body["requirement"]["validation_state"] in ("pass", "warn", "fail")
    assert len(body["validation_run"]["results"]) == 5


def test_validate_requirement_response_exposes_rule_codes_and_messages(client):
    requirement_id = _create_requirement_via_extraction(client)

    response = client.post(f"/requirements/{requirement_id}/validate")

    results = response.json()["validation_run"]["results"]
    codes = {r["rule_code"] for r in results}
    assert codes == {
        "DUPLICATE_NEAR",
        "AMBIGUOUS_WORDING",
        "MISSING_ACCEPTANCE_CONDITION",
        "MISSING_ACTOR",
        "POSSIBLE_CONTRADICTION",
    }
    for r in results:
        assert r["message"]


def test_validate_missing_requirement_returns_404(client):
    response = client.post("/requirements/999999/validate")
    assert response.status_code == 404


def test_get_validation_results_before_any_validation_returns_404(client):
    requirement_id = _create_requirement_via_extraction(client)

    response = client.get(f"/requirements/{requirement_id}/validation-results")

    assert response.status_code == 404


def test_get_validation_results_after_validation(client):
    requirement_id = _create_requirement_via_extraction(client)
    client.post(f"/requirements/{requirement_id}/validate")

    response = client.get(f"/requirements/{requirement_id}/validation-results")

    assert response.status_code == 200
    assert len(response.json()["results"]) == 5


def test_repeated_validation_produces_new_results_via_api(client):
    requirement_id = _create_requirement_via_extraction(client)
    first = client.post(f"/requirements/{requirement_id}/validate").json()
    second = client.post(f"/requirements/{requirement_id}/validate").json()

    assert first["validation_run"]["id"] != second["validation_run"]["id"]


# ---------------------------------------------------------------------------
# domain error mapping
# ---------------------------------------------------------------------------


def test_validation_configuration_error_mapped_to_500(client_and_sessionmaker):
    test_client, session_factory = client_and_sessionmaker
    requirement_id = _create_requirement_via_extraction(test_client)

    with session_factory() as s:
        s.execute(delete(ValidationRule).where(ValidationRule.code == "MISSING_ACTOR"))
        s.commit()

    response = test_client.post(f"/requirements/{requirement_id}/validate")

    assert response.status_code == 500
    assert "detail" in response.json()


def test_unexpected_exception_does_not_leak_internal_details(client):
    # TestClient defaults to re-raising unhandled server exceptions (so bugs
    # surface loudly during normal testing). This test specifically checks
    # the real over-the-wire HTTP behaviour our exception handler produces,
    # so it needs raise_server_exceptions=False to observe the actual
    # response instead of the re-raised exception.
    requirement_id = _create_requirement_via_extraction(client)
    no_raise_client = TestClient(app, raise_server_exceptions=False)

    with patch(
        "app.api.routes.requirements.run_validation",
        side_effect=RuntimeError("sensitive internal stack detail"),
    ):
        response = no_raise_client.post(f"/requirements/{requirement_id}/validate")

    assert response.status_code == 500
    body = response.json()
    assert "sensitive internal stack detail" not in json.dumps(body)
    assert body == {"detail": "An unexpected internal error occurred."}
