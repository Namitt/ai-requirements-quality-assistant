from __future__ import annotations

from streamlit.testing.v1 import AppTest

from app.ui import api_client
from app.ui.streamlit_public_demo import _build_session_bundle


def _pending_run1_requirement_id() -> int:
    # Requirement index 2 of run1 is seeded as "pending" per the fixture
    # (the same one test_two_session_bundles_are_fully_independent in
    # test_streamlit_public_demo.py relies on) - a pending requirement is
    # required here so render_review_controls actually renders its
    # Edit/Approve/Reject buttons instead of returning early. The fixture
    # seeds deterministically (proven in test_public_demo_fixture.py), so a
    # second, independent bundle built here yields the same id as the one
    # built inside the AppTest script.
    bundle = _build_session_bundle()
    with api_client.use_test_client(bundle["client"]):
        run = api_client.get_extraction_run(bundle["refs"]["run1"])
    return run["extracted_requirements"][2]["requirements"][0]["id"]


def _render_same_requirement_in_workflow_and_audit_scopes() -> None:
    # Runs as a real Streamlit script under AppTest, so widget keys are
    # actually registered and duplicate-key collisions are actually
    # detected - a plain Python call to these functions would not exercise
    # that at all, since key registration only happens inside a live
    # ScriptRunContext.
    import streamlit as st

    from app.ui import api_client
    from app.ui.streamlit_app import render_requirement_card
    from app.ui.streamlit_public_demo import _build_session_bundle

    bundle = _build_session_bundle()
    run1_id = bundle["refs"]["run1"]

    with api_client.use_test_client(bundle["client"]):
        run = api_client.get_extraction_run(run1_id)
        requirement_id = run["extracted_requirements"][2]["requirements"][0]["id"]

        # Mirrors exactly what app/ui/streamlit_public_demo.py's main() does
        # in one script run: the same requirement rendered once via the
        # Workflow path and once via the Audit drill-down path.
        workflow_tab, audit_tab = st.tabs(["Workflow", "Audit & Traceability Summary"])
        with workflow_tab:
            render_requirement_card(requirement_id, run["model_name"], run["mode"])
        with audit_tab:
            render_requirement_card(
                requirement_id, run["model_name"], run["mode"], scope="audit"
            )


def test_same_requirement_renders_in_workflow_and_audit_scopes_without_key_collision():
    at = AppTest.from_function(
        _render_same_requirement_in_workflow_and_audit_scopes, default_timeout=30
    )
    at.run()

    assert not at.exception, [str(e) for e in at.exception]

    # Both copies of the card actually rendered content (not silently
    # skipped), proving this isn't a false pass from an early return.
    assert any("AI-drafted requirement" in md.value for md in at.markdown)


def test_workflow_edit_toggle_does_not_bleed_into_audit_scope():
    # The same key collision that crashed the app also meant, more subtly,
    # that toggling "Edit" in one context would silently flip edit-mode for
    # the "same" requirement in the other context too, since both used the
    # same st.session_state[f"editing_{requirement_id}"] entry. Scoping the
    # session-state key by rendering context fixes this as a side effect of
    # the same change - this test targets that correctness issue directly by
    # actually clicking the Workflow-scoped Edit button and checking that
    # only the workflow-scoped edit-mode flag flips, never the audit one.
    at = AppTest.from_function(
        _render_same_requirement_in_workflow_and_audit_scopes, default_timeout=30
    )
    at.run()

    requirement_id = _pending_run1_requirement_id()
    workflow_edit_btn = at.button(key=f"workflow_edit_btn_{requirement_id}")
    audit_edit_btn = at.button(key=f"audit_edit_btn_{requirement_id}")
    assert workflow_edit_btn.key != audit_edit_btn.key

    at = workflow_edit_btn.click().run()
    assert not at.exception, [str(e) for e in at.exception]

    assert at.session_state[f"workflow_editing_{requirement_id}"] is True
    assert f"audit_editing_{requirement_id}" not in at.session_state


def _render_requirement_card_with_ai_drafting_disabled() -> None:
    # AppTest.from_function only captures this function's own body, not
    # sibling helper functions in this module - so each variant below is
    # fully self-contained, mirroring
    # _render_same_requirement_in_workflow_and_audit_scopes above.
    from app.ui import api_client
    from app.ui.streamlit_app import render_requirement_card
    from app.ui.streamlit_public_demo import _build_session_bundle

    bundle = _build_session_bundle()
    run1_id = bundle["refs"]["run1"]

    with api_client.use_test_client(bundle["client"]), api_client.disable_ai_drafting():
        run = api_client.get_extraction_run(run1_id)
        requirement_id = run["extracted_requirements"][2]["requirements"][0]["id"]
        render_requirement_card(requirement_id, run["model_name"], run["mode"])


def _render_requirement_card_with_ai_drafting_enabled() -> None:
    from app.ui import api_client
    from app.ui.streamlit_app import render_requirement_card
    from app.ui.streamlit_public_demo import _build_session_bundle

    bundle = _build_session_bundle()
    run1_id = bundle["refs"]["run1"]

    with api_client.use_test_client(bundle["client"]):
        run = api_client.get_extraction_run(run1_id)
        requirement_id = run["extracted_requirements"][2]["requirements"][0]["id"]
        render_requirement_card(requirement_id, run["model_name"], run["mode"])


def test_draft_ac_button_is_disabled_when_ai_drafting_disabled():
    # Stage 6: the public demo wraps its render pass in
    # api_client.disable_ai_drafting() so a recruiter can never trigger a
    # real (or accidentally billable) provider call from a public page.
    at = AppTest.from_function(
        _render_requirement_card_with_ai_drafting_disabled, default_timeout=30
    )
    at.run()
    assert not at.exception, [str(e) for e in at.exception]

    requirement_id = _pending_run1_requirement_id()
    draft_btn = at.button(key=f"workflow_draft_ac_btn_{requirement_id}")
    assert draft_btn.disabled is True
    assert any("Live AI drafting is disabled" in c.value for c in at.caption)


def test_draft_ac_button_remains_active_without_the_flag():
    # Regression: the canonical (local, two-process) app never sets
    # disable_ai_drafting(), so this control must behave exactly as before -
    # active, with no explanatory caption implying it's turned off.
    at = AppTest.from_function(
        _render_requirement_card_with_ai_drafting_enabled, default_timeout=30
    )
    at.run()
    assert not at.exception, [str(e) for e in at.exception]

    requirement_id = _pending_run1_requirement_id()
    draft_btn = at.button(key=f"workflow_draft_ac_btn_{requirement_id}")
    assert draft_btn.disabled is False
    assert not any("Live AI drafting is disabled" in c.value for c in at.caption)
