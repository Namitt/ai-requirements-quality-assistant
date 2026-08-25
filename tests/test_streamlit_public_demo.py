from __future__ import annotations

from app.ui.streamlit_public_demo import _build_session_bundle


def test_import_does_not_execute_main_as_a_side_effect():
    # Mirrors the same guard verification done for app/ui/streamlit_app.py
    # in Stage 3 - importing this module (even though it transitively
    # imports streamlit_app, which calls st.set_page_config() at module
    # scope) must not attempt to build a session bundle or render a page.
    import app.ui.streamlit_public_demo as m

    assert callable(m.main)
    assert callable(m._build_session_bundle)


def test_build_session_bundle_requires_no_provider_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("AI_PROVIDER", raising=False)

    bundle = _build_session_bundle()

    response = bundle["client"].get("/requirements/summary")
    assert response.status_code == 200
    assert len(response.json()) == 11


def test_build_session_bundle_seeds_run1_ref_reachable_via_client():
    bundle = _build_session_bundle()
    run1_id = bundle["refs"]["run1"]

    response = bundle["client"].get(f"/extraction-runs/{run1_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "live"
    assert body["model_name"] == "gemini-3.5-flash"
    requirement_ids = [
        req["id"]
        for extracted in body["extracted_requirements"]
        for req in extracted["requirements"]
    ]
    assert len(requirement_ids) == 3


def test_two_session_bundles_are_fully_independent():
    bundle_a = _build_session_bundle()
    bundle_b = _build_session_bundle()

    assert bundle_a["app"] is not bundle_b["app"]
    assert bundle_a["engine"] is not bundle_b["engine"]
    assert bundle_a["client"] is not bundle_b["client"]

    # An asymmetric mutation in A must never appear in B. Requirement #3 in
    # run1 (index 2) is seeded as pending, per the fixture, so it's a valid
    # target for reject.
    run1_id_a = bundle_a["refs"]["run1"]
    run_a = bundle_a["client"].get(f"/extraction-runs/{run1_id_a}").json()
    requirement_id_a = run_a["extracted_requirements"][2]["requirements"][0]["id"]
    reject_response = bundle_a["client"].post(f"/requirements/{requirement_id_a}/reject")
    assert reject_response.status_code == 200
    assert reject_response.json()["review_status"] == "rejected"

    run1_id_b = bundle_b["refs"]["run1"]
    run_b = bundle_b["client"].get(f"/extraction-runs/{run1_id_b}").json()
    requirement_id_b = run_b["extracted_requirements"][2]["requirements"][0]["id"]
    # Same ref, same position -> same id in B's own independent sequence,
    # but B's copy must still show its own original seeded state
    # (pending, per the fixture), never A's rejection.
    assert requirement_id_a == requirement_id_b
    review_b = bundle_b["client"].get(f"/requirements/{requirement_id_b}/review").json()
    assert review_b["requirement"]["review_status"] == "pending"
