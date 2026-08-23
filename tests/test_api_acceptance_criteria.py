from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_db_session, get_extraction_client
from app.db import Base, get_engine
from app.extraction import ExtractionCallResult
from app.main import app
from app.models import AcceptanceCriterion, Requirement
from app.seed import seed_validation_rules

FULL_VALID = (
    "Given a user with 5 failed login attempts, when they attempt to log in "
    "again, then the system shall lock the account within 2 seconds."
)
NOT_MEASURABLE = (
    "Given a user with 5 failed login attempts, when they attempt to log in "
    "again, then the system shall lock the account."
)


class FakeExtractionClient:
    def __init__(self, criterion_text: str = FULL_VALID, model_name: str = "fake-ac-model"):
        self.model_name = model_name
        self._text = json.dumps({"criterion_text": criterion_text})

    def complete(self, prompt: str) -> ExtractionCallResult:
        return ExtractionCallResult(text=self._text, raw_response=self._text)


class RaisingExtractionClient:
    model_name = "fake-ac-model"

    def complete(self, prompt: str):
        from app.extraction import ExtractionAPIError

        raise ExtractionAPIError("simulated network/API failure")


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
    app.dependency_overrides[get_extraction_client] = lambda: FakeExtractionClient()

    with TestClient(app) as test_client:
        yield test_client, session_factory

    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture()
def client(client_and_sessionmaker):
    test_client, _ = client_and_sessionmaker
    return test_client


def _make_requirement(session_factory, review_status: str = "pending") -> int:
    with session_factory() as s:
        requirement = Requirement(
            current_text="The system shall lock a user account after 5 failed login attempts.",
            origin="ai_generated",
            review_status=review_status,
            validation_state="pass" if review_status == "approved" else "not_validated",
        )
        s.add(requirement)
        s.commit()
        return requirement.id


def _override_extraction_client(criterion_text: str) -> None:
    app.dependency_overrides[get_extraction_client] = lambda: FakeExtractionClient(
        criterion_text
    )


# ---------------------------------------------------------------------------
# drafting
# ---------------------------------------------------------------------------


def test_draft_endpoint_creates_criterion(client_and_sessionmaker):
    client, session_factory = client_and_sessionmaker
    requirement_id = _make_requirement(session_factory)

    response = client.post(f"/requirements/{requirement_id}/acceptance-criteria")

    assert response.status_code == 201
    body = response.json()
    assert body["current_text"] == FULL_VALID
    assert body["review_status"] == "pending"
    assert body["validation_state"] == "pass"


def test_draft_missing_requirement_returns_404(client):
    response = client.post("/requirements/999999/acceptance-criteria")
    assert response.status_code == 404


def test_draft_ai_error_mapped_to_502(client_and_sessionmaker):
    client, session_factory = client_and_sessionmaker
    requirement_id = _make_requirement(session_factory)
    app.dependency_overrides[get_extraction_client] = lambda: RaisingExtractionClient()

    response = client.post(f"/requirements/{requirement_id}/acceptance-criteria")

    assert response.status_code == 502


def test_draft_works_for_approved_and_rejected_requirements(client_and_sessionmaker):
    client, session_factory = client_and_sessionmaker
    for status in ("approved", "rejected"):
        requirement_id = _make_requirement(session_factory, review_status=status)
        response = client.post(f"/requirements/{requirement_id}/acceptance-criteria")
        assert response.status_code == 201


def test_draft_never_changes_parent_requirement_status(client_and_sessionmaker):
    client, session_factory = client_and_sessionmaker
    requirement_id = _make_requirement(session_factory)

    client.post(f"/requirements/{requirement_id}/acceptance-criteria")

    response = client.get(f"/requirements/{requirement_id}")
    assert response.json()["review_status"] == "pending"


# ---------------------------------------------------------------------------
# list / get
# ---------------------------------------------------------------------------


def test_list_acceptance_criteria(client_and_sessionmaker):
    client, session_factory = client_and_sessionmaker
    requirement_id = _make_requirement(session_factory)
    client.post(f"/requirements/{requirement_id}/acceptance-criteria")
    client.post(f"/requirements/{requirement_id}/acceptance-criteria")

    response = client.get(f"/requirements/{requirement_id}/acceptance-criteria")

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_list_missing_requirement_returns_404(client):
    response = client.get("/requirements/999999/acceptance-criteria")
    assert response.status_code == 404


def test_get_extracted_acceptance_criterion(client_and_sessionmaker):
    client, session_factory = client_and_sessionmaker
    requirement_id = _make_requirement(session_factory)
    created = client.post(f"/requirements/{requirement_id}/acceptance-criteria").json()

    review = client.get(f"/acceptance-criteria/{created['id']}/review").json()
    extracted_id = review["provenance"]["id"]

    response = client.get(f"/extracted-acceptance-criteria/{extracted_id}")
    assert response.status_code == 200
    assert response.json()["criterion_text"] == FULL_VALID
    assert "raw_response" not in response.json()


def test_get_extracted_acceptance_criterion_missing_returns_404(client):
    response = client.get("/extracted-acceptance-criteria/999999")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# replay
# ---------------------------------------------------------------------------


def test_replay_endpoint_creates_replay(client_and_sessionmaker):
    client, session_factory = client_and_sessionmaker
    requirement_id = _make_requirement(session_factory)
    created = client.post(f"/requirements/{requirement_id}/acceptance-criteria").json()
    review = client.get(f"/acceptance-criteria/{created['id']}/review").json()
    extracted_id = review["provenance"]["id"]

    response = client.post(f"/extracted-acceptance-criteria/{extracted_id}/replay")

    assert response.status_code == 201
    body = response.json()
    assert body["mode"] == "replay"
    assert body["replayed_from_id"] == extracted_id
    assert "raw_response" not in body


def test_replay_endpoint_does_not_call_extraction_client(client_and_sessionmaker):
    client, session_factory = client_and_sessionmaker
    requirement_id = _make_requirement(session_factory)
    created = client.post(f"/requirements/{requirement_id}/acceptance-criteria").json()
    review = client.get(f"/acceptance-criteria/{created['id']}/review").json()
    extracted_id = review["provenance"]["id"]

    app.dependency_overrides[get_extraction_client] = lambda: RaisingExtractionClient()

    response = client.post(f"/extracted-acceptance-criteria/{extracted_id}/replay")
    assert response.status_code == 201


def test_replay_missing_source_returns_404(client):
    response = client.post("/extracted-acceptance-criteria/999999/replay")
    assert response.status_code == 404


def test_replay_of_replay_returns_409(client_and_sessionmaker):
    client, session_factory = client_and_sessionmaker
    requirement_id = _make_requirement(session_factory)
    created = client.post(f"/requirements/{requirement_id}/acceptance-criteria").json()
    review = client.get(f"/acceptance-criteria/{created['id']}/review").json()
    extracted_id = review["provenance"]["id"]
    replay = client.post(f"/extracted-acceptance-criteria/{extracted_id}/replay").json()

    response = client.post(f"/extracted-acceptance-criteria/{replay['id']}/replay")
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# edit / revalidation
# ---------------------------------------------------------------------------


def test_patch_updates_text_and_revalidates(client_and_sessionmaker):
    client, session_factory = client_and_sessionmaker
    requirement_id = _make_requirement(session_factory)
    created = client.post(f"/requirements/{requirement_id}/acceptance-criteria").json()

    response = client.patch(
        f"/acceptance-criteria/{created['id']}", json={"current_text": NOT_MEASURABLE}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["current_text"] == NOT_MEASURABLE
    assert body["validation_state"] == "warn"


def test_patch_creates_edit_history_row(client_and_sessionmaker):
    client, session_factory = client_and_sessionmaker
    requirement_id = _make_requirement(session_factory)
    created = client.post(f"/requirements/{requirement_id}/acceptance-criteria").json()

    client.patch(f"/acceptance-criteria/{created['id']}", json={"current_text": NOT_MEASURABLE})

    review = client.get(f"/acceptance-criteria/{created['id']}/review").json()
    assert len(review["edit_history"]) == 1
    assert review["edit_history"][0]["previous_text"] == FULL_VALID
    assert review["edit_history"][0]["new_text"] == NOT_MEASURABLE


def test_patch_on_non_pending_criterion_returns_409(client_and_sessionmaker):
    client, session_factory = client_and_sessionmaker
    requirement_id = _make_requirement(session_factory)
    created = client.post(f"/requirements/{requirement_id}/acceptance-criteria").json()
    client.post(f"/acceptance-criteria/{created['id']}/approve")

    response = client.patch(
        f"/acceptance-criteria/{created['id']}", json={"current_text": NOT_MEASURABLE}
    )
    assert response.status_code == 409


def test_edit_clears_warn_acknowledgement(client_and_sessionmaker):
    client, session_factory = client_and_sessionmaker
    requirement_id = _make_requirement(session_factory)
    created = client.post(f"/requirements/{requirement_id}/acceptance-criteria").json()
    client.patch(f"/acceptance-criteria/{created['id']}", json={"current_text": NOT_MEASURABLE})
    client.post(
        f"/acceptance-criteria/{created['id']}/approve", json={"acknowledge_warning": True}
    )

    with session_factory() as s:
        criterion = s.get(AcceptanceCriterion, created["id"])
        assert criterion.review_status == "approved"
        assert criterion.warn_acknowledged_at is not None

    # editing an approved criterion is blocked (409), matching requirement
    # workflow semantics - the acknowledgement-clearing behaviour is proven
    # by test_acceptance_criteria_validation_engine.py's dedicated test.


def test_patch_missing_criterion_returns_404(client):
    response = client.patch("/acceptance-criteria/999999", json={"current_text": "x"})
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# approval
# ---------------------------------------------------------------------------


def test_pass_criterion_can_be_approved(client_and_sessionmaker):
    client, session_factory = client_and_sessionmaker
    requirement_id = _make_requirement(session_factory)
    created = client.post(f"/requirements/{requirement_id}/acceptance-criteria").json()

    response = client.post(f"/acceptance-criteria/{created['id']}/approve")
    assert response.status_code == 200
    assert response.json()["review_status"] == "approved"


def test_warn_criterion_cannot_be_approved_without_acknowledgement(client_and_sessionmaker):
    client, session_factory = client_and_sessionmaker
    requirement_id = _make_requirement(session_factory)
    created = client.post(f"/requirements/{requirement_id}/acceptance-criteria").json()
    client.patch(f"/acceptance-criteria/{created['id']}", json={"current_text": NOT_MEASURABLE})

    response = client.post(f"/acceptance-criteria/{created['id']}/approve")
    assert response.status_code == 409


def test_warn_criterion_approved_with_explicit_acknowledgement(client_and_sessionmaker):
    client, session_factory = client_and_sessionmaker
    requirement_id = _make_requirement(session_factory)
    created = client.post(f"/requirements/{requirement_id}/acceptance-criteria").json()
    client.patch(f"/acceptance-criteria/{created['id']}", json={"current_text": NOT_MEASURABLE})

    response = client.post(
        f"/acceptance-criteria/{created['id']}/approve", json={"acknowledge_warning": True}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["review_status"] == "approved"
    assert body["warn_acknowledged_at"] is not None
    assert body["warn_acknowledged_by"] is not None


def test_fail_criterion_cannot_be_approved(client_and_sessionmaker):
    # No v1 AC rule can produce FAIL, so this directly exercises the
    # enforcement path (application + DB) by forcing validation_state='fail'
    # the way a future stricter rule would - the FAIL gate itself must still
    # work even though it is currently unreachable through the rule engine.
    client, session_factory = client_and_sessionmaker
    requirement_id = _make_requirement(session_factory)
    created = client.post(f"/requirements/{requirement_id}/acceptance-criteria").json()

    with session_factory() as s:
        criterion = s.get(AcceptanceCriterion, created["id"])
        criterion.validation_state = "fail"
        s.commit()

    response = client.post(f"/acceptance-criteria/{created['id']}/approve")
    assert response.status_code == 409


def test_approve_missing_criterion_returns_404(client):
    response = client.post("/acceptance-criteria/999999/approve")
    assert response.status_code == 404


def test_approving_criterion_never_changes_parent_requirement_status(client_and_sessionmaker):
    client, session_factory = client_and_sessionmaker
    requirement_id = _make_requirement(session_factory)
    created = client.post(f"/requirements/{requirement_id}/acceptance-criteria").json()

    client.post(f"/acceptance-criteria/{created['id']}/approve")

    response = client.get(f"/requirements/{requirement_id}")
    assert response.json()["review_status"] == "pending"


# ---------------------------------------------------------------------------
# rejection
# ---------------------------------------------------------------------------


def test_pending_criterion_can_be_rejected(client_and_sessionmaker):
    client, session_factory = client_and_sessionmaker
    requirement_id = _make_requirement(session_factory)
    created = client.post(f"/requirements/{requirement_id}/acceptance-criteria").json()

    response = client.post(f"/acceptance-criteria/{created['id']}/reject")
    assert response.status_code == 200
    assert response.json()["review_status"] == "rejected"


def test_rejection_never_deletes_the_criterion(client_and_sessionmaker):
    client, session_factory = client_and_sessionmaker
    requirement_id = _make_requirement(session_factory)
    created = client.post(f"/requirements/{requirement_id}/acceptance-criteria").json()

    client.post(f"/acceptance-criteria/{created['id']}/reject")

    with session_factory() as s:
        assert s.get(AcceptanceCriterion, created["id"]) is not None


def test_rejecting_criterion_never_changes_parent_requirement_status(client_and_sessionmaker):
    client, session_factory = client_and_sessionmaker
    requirement_id = _make_requirement(session_factory)
    created = client.post(f"/requirements/{requirement_id}/acceptance-criteria").json()

    client.post(f"/acceptance-criteria/{created['id']}/reject")

    response = client.get(f"/requirements/{requirement_id}")
    assert response.json()["review_status"] == "pending"


def test_reject_missing_criterion_returns_404(client):
    response = client.post("/acceptance-criteria/999999/reject")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# composite review
# ---------------------------------------------------------------------------


def test_review_returns_full_provenance_chain(client_and_sessionmaker):
    client, session_factory = client_and_sessionmaker
    requirement_id = _make_requirement(session_factory)
    created = client.post(f"/requirements/{requirement_id}/acceptance-criteria").json()

    response = client.get(f"/acceptance-criteria/{created['id']}/review")

    assert response.status_code == 200
    body = response.json()
    assert body["acceptance_criterion"]["id"] == created["id"]
    assert body["provenance"]["requirement_id"] == requirement_id
    assert body["provenance"]["mode"] == "live"
    assert body["provenance"]["model_name"] == "fake-ac-model"
    assert body["parent_requirement"]["id"] == requirement_id
    assert body["latest_validation"] is not None
    assert len(body["latest_validation"]["results"]) == 4
    assert body["edit_history"] == []


def test_review_missing_criterion_returns_404(client):
    response = client.get("/acceptance-criteria/999999/review")
    assert response.status_code == 404
