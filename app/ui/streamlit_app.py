from __future__ import annotations

import streamlit as st

from app.ui import api_client
from app.ui.api_client import APIClientError
from app.ui.demo_fixture import DEMO_SOURCE_TEXT, DEMO_TITLE

st.set_page_config(page_title="AI Requirements & Traceability Workbench", layout="wide")

VALIDATION_ICONS = {"pass": "✅", "warn": "⚠️", "fail": "❌"}
REVIEW_ICONS = {"pending": "🕒", "approved": "✅", "rejected": "🚫"}


def _load_demo_scenario() -> None:
    st.session_state["source_text_input"] = DEMO_SOURCE_TEXT
    st.session_state["title_input"] = DEMO_TITLE


def render_header() -> None:
    st.title("AI Requirements & Traceability Workbench")
    st.caption(
        "Turn messy stakeholder input into traceable, validated requirements "
        "— with AI drafting, deterministic quality checks, and human approval."
    )
    cols = st.columns(4)
    for col, step in zip(cols, ["1. Extract", "2. Validate", "3. Review", "4. Approve"]):
        col.markdown(f"**{step}**")
    st.divider()


def render_input_section() -> None:
    st.subheader("1. Add stakeholder input")
    st.write(
        "Paste meeting notes, an interview transcript, email text, or other "
        "unstructured discovery material."
    )
    st.button("Load Demo Scenario", on_click=_load_demo_scenario)
    title = st.text_input("Title (optional)", key="title_input")
    raw_text = st.text_area("Source text", height=220, key="source_text_input")

    if st.button("Extract Requirements", type="primary"):
        if not raw_text.strip():
            st.error("Please paste some source text first.")
        else:
            _run_extraction(raw_text, title or None)

    st.divider()


def _run_extraction(raw_text: str, title: str | None) -> None:
    try:
        with st.spinner("AI extraction in progress..."):
            run = api_client.extract_requirements(raw_text, title)
    except APIClientError as exc:
        st.error(f"Extraction could not be completed. {exc}")
        return

    requirement_ids = [
        req["id"]
        for extracted in run["extracted_requirements"]
        for req in extracted["requirements"]
    ]

    if requirement_ids:
        # A distinct, visible second stage: deterministic rules checking the
        # AI's draft. This is never presented as something the AI did.
        with st.spinner(
            f"Running deterministic validation on {len(requirement_ids)} "
            "requirement(s) — independent, fixed rule checks, not the AI..."
        ):
            for requirement_id in requirement_ids:
                try:
                    api_client.validate_requirement(requirement_id)
                except APIClientError as exc:
                    st.warning(
                        f"Validation could not be completed for requirement "
                        f"#{requirement_id}. {exc}"
                    )

    st.session_state["extraction_run_id"] = run["id"]
    st.success(f"Extracted {len(requirement_ids)} candidate requirement(s).")


def render_replay_section() -> None:
    st.subheader("1b. Or, replay a previous extraction")
    st.write(
        "Re-run a past AI extraction's results through validation and review "
        "again, without making a new live AI call — useful for demonstrating "
        "the workflow without a network connection or API key."
    )

    try:
        runs = api_client.list_extraction_runs()
    except APIClientError as exc:
        st.error(f"Could not load past extraction runs. {exc}")
        st.divider()
        return

    # Only a live run can be replayed, and a replay can never itself be
    # replayed - the backend enforces this too, but filtering here keeps the
    # dropdown limited to choices that will actually succeed.
    live_runs = [run for run in runs if run["mode"] == "live"]

    if not live_runs:
        st.caption("No live extraction runs are available to replay yet.")
        st.divider()
        return

    options = {
        f"Run #{run['id']} — {run['model_name']} — {run['run_at']}": run["id"]
        for run in live_runs
    }
    selected_label = st.selectbox("Choose a live extraction run to replay", options.keys())

    if st.button("Replay Selected Run"):
        selected_id = options[selected_label]
        try:
            with st.spinner("Replaying extraction (no live AI call)..."):
                replay_run = api_client.replay_extraction(selected_id)
        except APIClientError as exc:
            st.error(f"Replay could not be completed. {exc}")
            st.divider()
            return

        st.session_state["extraction_run_id"] = replay_run["id"]
        st.success(f"Replayed run #{selected_id} as new run #{replay_run['id']}.")

    st.divider()


def render_results_section() -> None:
    extraction_run_id = st.session_state.get("extraction_run_id")
    if extraction_run_id is None:
        return

    try:
        run = api_client.get_extraction_run(extraction_run_id)
    except APIClientError as exc:
        st.error(f"Could not load extraction results. {exc}")
        return

    requirement_ids = [
        req["id"]
        for extracted in run["extracted_requirements"]
        for req in extracted["requirements"]
    ]

    if not requirement_ids:
        st.info("This extraction produced no candidate requirements.")
        return

    st.subheader("2–4. Extracted requirements, validation & review")
    st.write(
        "Each card below shows what the AI drafted, the exact source text it "
        "came from, and the result of an independent, deterministic quality "
        "check — the AI has no influence over that check, and no influence "
        "over the approval decision either."
    )

    for requirement_id in requirement_ids:
        render_requirement_card(requirement_id)


def render_requirement_card(requirement_id: int) -> None:
    try:
        review = api_client.get_requirement_review(requirement_id)
    except APIClientError as exc:
        st.error(f"Could not load requirement #{requirement_id}. {exc}")
        return

    requirement = review["requirement"]
    evidence = review["extracted_evidence"]
    validation = review["latest_validation"]

    state_icon = VALIDATION_ICONS.get(requirement["validation_state"], "❔")
    status_icon = REVIEW_ICONS.get(requirement["review_status"], "")

    with st.container(border=True):
        st.markdown(
            f"**Requirement #{requirement_id}** &nbsp; {state_icon} "
            f"`{requirement['validation_state'].upper()}` &nbsp; {status_icon} "
            f"`{requirement['review_status'].upper()}`"
        )

        st.markdown("**🤖 AI-drafted requirement**")
        st.write(requirement["current_text"])

        if evidence is not None:
            st.markdown("**📄 Source evidence**")
            st.markdown(f"> {evidence['source_quote']}")
            st.caption(f"Source document #{evidence['source_document_id']}")

        st.markdown(
            "**🔎 Deterministic validation** — checked independently of the "
            "AI, using fixed rules"
        )
        if validation is None:
            st.caption("Not yet validated.")
        else:
            for result in validation["results"]:
                icon = VALIDATION_ICONS.get(result["result"], "❔")
                with st.expander(
                    f"{icon} {result['rule_code']} — {result['result'].upper()}"
                ):
                    st.write(result["message"])
                    if result["recommended_action"]:
                        st.caption(f"Recommended action: {result['recommended_action']}")

        render_review_controls(requirement, review["edit_history"])

        render_acceptance_criteria_section(requirement_id)


def render_review_controls(requirement: dict, edit_history: list[dict]) -> None:
    requirement_id = requirement["id"]
    st.markdown("**🧑 Human review**")

    if edit_history:
        with st.expander(f"Edit history ({len(edit_history)})"):
            for edit in edit_history:
                st.markdown(f"*{edit['edited_at']} — edited by {edit['edited_by'] or 'unknown'}*")
                st.markdown(f"- Before: {edit['previous_text']}")
                st.markdown(f"- After: {edit['new_text']}")
                st.divider()

    if requirement["review_status"] != "pending":
        st.caption(
            f"This requirement has already been {requirement['review_status']}. "
            "No further action available."
        )
        return

    edit_key = f"editing_{requirement_id}"
    edit_col, approve_col, reject_col = st.columns(3)

    if edit_col.button("Edit", key=f"edit_btn_{requirement_id}"):
        st.session_state[edit_key] = not st.session_state.get(edit_key, False)

    if st.session_state.get(edit_key):
        new_text = st.text_area(
            "Edit requirement text",
            value=requirement["current_text"],
            key=f"edit_text_{requirement_id}",
        )
        if st.button("Save edit", key=f"save_edit_{requirement_id}"):
            try:
                api_client.patch_requirement(requirement_id, new_text)
                st.session_state[edit_key] = False
                st.success("Requirement updated and re-validated.")
                st.rerun()
            except APIClientError as exc:
                st.error(f"Could not save the edit. {exc}")

    validation_state = requirement["validation_state"]

    if validation_state == "fail":
        approve_col.button("Approve", key=f"approve_btn_{requirement_id}", disabled=True)
        approve_col.caption("Blocked: FAIL result cannot be approved.")
    elif validation_state == "warn":
        acknowledge = approve_col.checkbox(
            "I have reviewed the warning; it does not block approval",
            key=f"ack_{requirement_id}",
        )
        if approve_col.button(
            "Approve", key=f"approve_btn_{requirement_id}", disabled=not acknowledge
        ):
            _approve(requirement_id, acknowledge_warning=True)
    else:
        if approve_col.button("Approve", key=f"approve_btn_{requirement_id}"):
            _approve(requirement_id, acknowledge_warning=False)

    if reject_col.button("Reject", key=f"reject_btn_{requirement_id}"):
        try:
            api_client.reject_requirement(requirement_id)
            st.success("Requirement rejected.")
            st.rerun()
        except APIClientError as exc:
            st.error(f"Could not reject the requirement. {exc}")


def _approve(requirement_id: int, acknowledge_warning: bool) -> None:
    try:
        api_client.approve_requirement(requirement_id, acknowledge_warning=acknowledge_warning)
        st.success("Requirement approved.")
        st.rerun()
    except APIClientError as exc:
        st.error(f"Could not approve the requirement. {exc}")


def render_acceptance_criteria_section(requirement_id: int) -> None:
    st.markdown("**📋 Acceptance criteria**")
    st.caption(
        "AI-drafted Given/When/Then criteria for this requirement, checked "
        "by four independent structural rules, and reviewed separately from "
        "the requirement itself — approving or rejecting one never changes "
        "the requirement's own review status."
    )

    if st.button("Draft Acceptance Criteria", key=f"draft_ac_btn_{requirement_id}"):
        try:
            with st.spinner("Drafting acceptance criterion..."):
                api_client.draft_acceptance_criteria(requirement_id)
            st.rerun()
        except APIClientError as exc:
            st.error(f"Could not draft acceptance criteria. {exc}")

    try:
        criteria = api_client.list_acceptance_criteria(requirement_id)
    except APIClientError as exc:
        st.error(f"Could not load acceptance criteria. {exc}")
        return

    if not criteria:
        st.caption("No acceptance criteria drafted yet.")
        return

    # Populated while rendering each criterion below, from that criterion's
    # own provenance - only live-mode drafts belonging to this requirement
    # are ever offered for replay, and a replay is never offered as a
    # replay source itself.
    live_extracted_options: dict[str, int] = {}

    for criterion in criteria:
        render_acceptance_criterion_card(criterion["id"], live_extracted_options)

    if live_extracted_options:
        with st.expander("Replay a previous live draft"):
            selected_label = st.selectbox(
                "Choose a previous live draft to replay",
                live_extracted_options.keys(),
                key=f"ac_replay_select_{requirement_id}",
            )
            if st.button("Replay Selected Draft", key=f"ac_replay_btn_{requirement_id}"):
                extracted_id = live_extracted_options[selected_label]
                try:
                    with st.spinner(
                        "Replaying acceptance criterion (no live AI call)..."
                    ):
                        api_client.replay_acceptance_criteria(extracted_id)
                    st.rerun()
                except APIClientError as exc:
                    st.error(f"Replay could not be completed. {exc}")


def render_acceptance_criterion_card(
    acceptance_criterion_id: int, live_extracted_options: dict[str, int]
) -> None:
    try:
        review = api_client.get_acceptance_criteria_review(acceptance_criterion_id)
    except APIClientError as exc:
        st.error(f"Could not load acceptance criterion #{acceptance_criterion_id}. {exc}")
        return

    criterion = review["acceptance_criterion"]
    provenance = review["provenance"]
    validation = review["latest_validation"]

    if provenance["mode"] == "live":
        label = f"AC #{criterion['id']} — drafted {provenance['created_at']}"
        live_extracted_options[label] = provenance["id"]

    state_icon = VALIDATION_ICONS.get(criterion["validation_state"], "❔")
    status_icon = REVIEW_ICONS.get(criterion["review_status"], "")
    mode_label = "🔁 replayed" if provenance["mode"] == "replay" else "🤖 live draft"

    with st.container(border=True):
        st.markdown(
            f"**Acceptance criterion #{criterion['id']}** ({mode_label}) &nbsp; "
            f"{state_icon} `{criterion['validation_state'].upper()}` &nbsp; "
            f"{status_icon} `{criterion['review_status'].upper()}`"
        )

        st.markdown("**🤖 AI-drafted criterion**")
        st.write(criterion["current_text"])

        st.markdown(
            "**🔎 Deterministic structural validation** — checks for a "
            "Given, When, and Then clause and a measurable Then condition; "
            "not a claim of business correctness or QA-readiness"
        )
        if validation is None:
            st.caption("Not yet validated.")
        else:
            for result in validation["results"]:
                icon = VALIDATION_ICONS.get(result["result"], "❔")
                with st.expander(
                    f"{icon} {result['rule_code']} — {result['result'].upper()}"
                ):
                    st.write(result["message"])
                    if result["recommended_action"]:
                        st.caption(f"Recommended action: {result['recommended_action']}")

        render_acceptance_criteria_review_controls(criterion, review["edit_history"])


def render_acceptance_criteria_review_controls(
    criterion: dict, edit_history: list[dict]
) -> None:
    acceptance_criterion_id = criterion["id"]
    st.markdown("**🧑 Human review (acceptance criterion)**")

    if edit_history:
        with st.expander(f"Edit history ({len(edit_history)})"):
            for edit in edit_history:
                st.markdown(
                    f"*{edit['edited_at']} — edited by {edit['edited_by'] or 'unknown'}*"
                )
                st.markdown(f"- Before: {edit['previous_text']}")
                st.markdown(f"- After: {edit['new_text']}")
                st.divider()

    if criterion["review_status"] != "pending":
        st.caption(
            f"This acceptance criterion has already been "
            f"{criterion['review_status']}. No further action available."
        )
        return

    edit_key = f"editing_ac_{acceptance_criterion_id}"
    edit_col, approve_col, reject_col = st.columns(3)

    if edit_col.button("Edit", key=f"edit_ac_btn_{acceptance_criterion_id}"):
        st.session_state[edit_key] = not st.session_state.get(edit_key, False)

    if st.session_state.get(edit_key):
        new_text = st.text_area(
            "Edit acceptance criterion text",
            value=criterion["current_text"],
            key=f"edit_ac_text_{acceptance_criterion_id}",
        )
        if st.button("Save edit", key=f"save_ac_edit_{acceptance_criterion_id}"):
            try:
                api_client.patch_acceptance_criteria(acceptance_criterion_id, new_text)
                st.session_state[edit_key] = False
                st.success("Acceptance criterion updated and re-validated.")
                st.rerun()
            except APIClientError as exc:
                st.error(f"Could not save the edit. {exc}")

    validation_state = criterion["validation_state"]

    if validation_state == "fail":
        approve_col.button(
            "Approve", key=f"approve_ac_btn_{acceptance_criterion_id}", disabled=True
        )
        approve_col.caption("Blocked: FAIL result cannot be approved.")
    elif validation_state == "warn":
        acknowledge = approve_col.checkbox(
            "I have reviewed the warning; it does not block approval",
            key=f"ack_ac_{acceptance_criterion_id}",
        )
        if approve_col.button(
            "Approve",
            key=f"approve_ac_btn_{acceptance_criterion_id}",
            disabled=not acknowledge,
        ):
            _approve_acceptance_criterion(acceptance_criterion_id, acknowledge_warning=True)
    else:
        if approve_col.button("Approve", key=f"approve_ac_btn_{acceptance_criterion_id}"):
            _approve_acceptance_criterion(acceptance_criterion_id, acknowledge_warning=False)

    if reject_col.button("Reject", key=f"reject_ac_btn_{acceptance_criterion_id}"):
        try:
            api_client.reject_acceptance_criteria(acceptance_criterion_id)
            st.success("Acceptance criterion rejected.")
            st.rerun()
        except APIClientError as exc:
            st.error(f"Could not reject the acceptance criterion. {exc}")


def _approve_acceptance_criterion(
    acceptance_criterion_id: int, acknowledge_warning: bool
) -> None:
    try:
        api_client.approve_acceptance_criteria(
            acceptance_criterion_id, acknowledge_warning=acknowledge_warning
        )
        st.success("Acceptance criterion approved.")
        st.rerun()
    except APIClientError as exc:
        st.error(f"Could not approve the acceptance criterion. {exc}")


def main() -> None:
    render_header()
    render_input_section()
    render_replay_section()
    render_results_section()


main()
