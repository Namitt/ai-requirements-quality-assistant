from __future__ import annotations

import sys
from pathlib import Path

# Streamlit's CLI only ever adds this script's own directory (app/ui) to
# sys.path, never the repository root - the `from app...` imports below
# would raise ModuleNotFoundError: No module named 'app' under a real
# `streamlit run` invocation (confirmed locally with the bare CLI entry
# point, the same one Streamlit Community Cloud uses). `python -m
# streamlit run` masks this because `-m` separately adds the current
# working directory - this is why it was never caught before. Resolved
# from __file__, not the working directory, so it is correct regardless
# of where the process is launched from.
_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import streamlit as st

from app.ui import api_client
from app.ui.api_client import APIClientError
from app.ui.demo_fixture import DEMO_SOURCE_TEXT, DEMO_TITLE

st.set_page_config(page_title="AI Requirements & Traceability Workbench", layout="wide")

VALIDATION_ICONS = {"pass": "✅", "warn": "⚠️", "fail": "❌"}
REVIEW_ICONS = {"pending": "🕒", "approved": "✅", "rejected": "🚫"}


def _provenance_caption(model_name: str, mode: str) -> str:
    return f"{model_name} · {'live' if mode == 'live' else 'replayed'}"


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
        render_requirement_card(requirement_id, run["model_name"], run["mode"])


def render_requirement_card(
    requirement_id: int, model_name: str, mode: str, scope: str = "workflow"
) -> None:
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
        st.caption(_provenance_caption(model_name, mode))
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

        render_review_controls(requirement, review["edit_history"], scope)

        render_acceptance_criteria_section(requirement_id, scope)


def render_review_controls(
    requirement: dict, edit_history: list[dict], scope: str = "workflow"
) -> None:
    # scope disambiguates widget/session-state keys when the same requirement
    # is rendered from more than one place in one script run (e.g. the
    # Workflow tab and the Audit tab's drill-down both call this) - without
    # it, Streamlit raises StreamlitDuplicateElementKey, and the two contexts
    # would also silently share edit-mode state via st.session_state.
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

    edit_key = f"{scope}_editing_{requirement_id}"
    edit_col, approve_col, reject_col = st.columns(3)

    if edit_col.button("Edit", key=f"{scope}_edit_btn_{requirement_id}"):
        st.session_state[edit_key] = not st.session_state.get(edit_key, False)

    if st.session_state.get(edit_key):
        new_text = st.text_area(
            "Edit requirement text",
            value=requirement["current_text"],
            key=f"{scope}_edit_text_{requirement_id}",
        )
        if st.button("Save edit", key=f"{scope}_save_edit_{requirement_id}"):
            try:
                api_client.patch_requirement(requirement_id, new_text)
                st.session_state[edit_key] = False
                st.success("Requirement updated and re-validated.")
                st.rerun()
            except APIClientError as exc:
                st.error(f"Could not save the edit. {exc}")

    validation_state = requirement["validation_state"]

    if validation_state == "fail":
        approve_col.button(
            "Approve", key=f"{scope}_approve_btn_{requirement_id}", disabled=True
        )
        approve_col.caption("Blocked: FAIL result cannot be approved.")
    elif validation_state == "warn":
        acknowledge = approve_col.checkbox(
            "I have reviewed the warning; it does not block approval",
            key=f"{scope}_ack_{requirement_id}",
        )
        if approve_col.button(
            "Approve", key=f"{scope}_approve_btn_{requirement_id}", disabled=not acknowledge
        ):
            _approve(requirement_id, acknowledge_warning=True)
    else:
        if approve_col.button("Approve", key=f"{scope}_approve_btn_{requirement_id}"):
            _approve(requirement_id, acknowledge_warning=False)

    if reject_col.button("Reject", key=f"{scope}_reject_btn_{requirement_id}"):
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


def render_acceptance_criteria_section(requirement_id: int, scope: str = "workflow") -> None:
    st.markdown("**📋 Acceptance criteria**")
    st.caption(
        "AI-drafted Given/When/Then criteria for this requirement, checked "
        "by four independent structural rules, and reviewed separately from "
        "the requirement itself — approving or rejecting one never changes "
        "the requirement's own review status."
    )

    if api_client.ai_drafting_disabled():
        st.button(
            "Draft Acceptance Criteria",
            key=f"{scope}_draft_ac_btn_{requirement_id}",
            disabled=True,
        )
        st.caption(
            "Live AI drafting is disabled in this public demo to avoid "
            "triggering a real provider call from a public page. Any "
            "acceptance criteria shown below were captured earlier from a "
            "genuine AI drafting call."
        )
    elif st.button("Draft Acceptance Criteria", key=f"{scope}_draft_ac_btn_{requirement_id}"):
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
        render_acceptance_criterion_card(criterion["id"], live_extracted_options, scope)

    if live_extracted_options:
        with st.expander("Replay a previous live draft"):
            selected_label = st.selectbox(
                "Choose a previous live draft to replay",
                live_extracted_options.keys(),
                key=f"{scope}_ac_replay_select_{requirement_id}",
            )
            if st.button("Replay Selected Draft", key=f"{scope}_ac_replay_btn_{requirement_id}"):
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
    acceptance_criterion_id: int,
    live_extracted_options: dict[str, int],
    scope: str = "workflow",
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
        st.caption(_provenance_caption(provenance["model_name"], provenance["mode"]))
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

        render_acceptance_criteria_review_controls(criterion, review["edit_history"], scope)


def render_acceptance_criteria_review_controls(
    criterion: dict, edit_history: list[dict], scope: str = "workflow"
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

    edit_key = f"{scope}_editing_ac_{acceptance_criterion_id}"
    edit_col, approve_col, reject_col = st.columns(3)

    if edit_col.button("Edit", key=f"{scope}_edit_ac_btn_{acceptance_criterion_id}"):
        st.session_state[edit_key] = not st.session_state.get(edit_key, False)

    if st.session_state.get(edit_key):
        new_text = st.text_area(
            "Edit acceptance criterion text",
            value=criterion["current_text"],
            key=f"{scope}_edit_ac_text_{acceptance_criterion_id}",
        )
        if st.button("Save edit", key=f"{scope}_save_ac_edit_{acceptance_criterion_id}"):
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
            "Approve",
            key=f"{scope}_approve_ac_btn_{acceptance_criterion_id}",
            disabled=True,
        )
        approve_col.caption("Blocked: FAIL result cannot be approved.")
    elif validation_state == "warn":
        acknowledge = approve_col.checkbox(
            "I have reviewed the warning; it does not block approval",
            key=f"{scope}_ack_ac_{acceptance_criterion_id}",
        )
        if approve_col.button(
            "Approve",
            key=f"{scope}_approve_ac_btn_{acceptance_criterion_id}",
            disabled=not acknowledge,
        ):
            _approve_acceptance_criterion(acceptance_criterion_id, acknowledge_warning=True)
    else:
        if approve_col.button(
            "Approve", key=f"{scope}_approve_ac_btn_{acceptance_criterion_id}"
        ):
            _approve_acceptance_criterion(acceptance_criterion_id, acknowledge_warning=False)

    if reject_col.button("Reject", key=f"{scope}_reject_ac_btn_{acceptance_criterion_id}"):
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


def _source_document_label(row: dict) -> str:
    if row["source_document_id"] is None:
        return "—"
    title = row["source_document_title"]
    return title if title else f"Document #{row['source_document_id']}"


def _summary_provenance_label(row: dict) -> str:
    if row["model_name"] is None or row["mode"] is None:
        return "—"
    return _provenance_caption(row["model_name"], row["mode"])


_VALIDATION_SORT_RANK = {"fail": 0, "warn": 1, "pass": 2, "not_validated": 3}
_REVIEW_SORT_RANK = {"pending": 0, "approved": 1, "rejected": 2}


def render_audit_summary_section() -> None:
    st.subheader("Audit & Traceability Summary")
    st.write(
        "Every requirement drafted so far, across all source documents and "
        "extraction runs — where each one currently stands, and what is "
        "still blocking a human decision. AI drafts, deterministic rules "
        "validate, a human decides — this view is a triage surface over "
        "that pipeline, not a replacement for the detailed review above."
    )

    try:
        summary = api_client.get_requirements_summary()
    except APIClientError as exc:
        st.error(f"Could not load the audit summary. {exc}")
        return

    if not summary:
        st.info("No requirements have been extracted yet.")
        return

    filter_cols = st.columns(3)
    review_options = ["All"] + sorted({row["review_status"] for row in summary})
    validation_options = ["All"] + sorted({row["validation_state"] for row in summary})
    document_options = ["All"] + sorted({_source_document_label(row) for row in summary})

    review_filter = filter_cols[0].selectbox("Review status", review_options)
    validation_filter = filter_cols[1].selectbox("Validation state", validation_options)
    document_filter = filter_cols[2].selectbox("Source document", document_options)

    sort_choice = st.selectbox(
        "Sort by",
        ["ID", "Validation state (worst first)", "Review status (pending first)"],
    )

    filtered = [
        row
        for row in summary
        if (review_filter == "All" or row["review_status"] == review_filter)
        and (validation_filter == "All" or row["validation_state"] == validation_filter)
        and (document_filter == "All" or _source_document_label(row) == document_filter)
    ]

    if sort_choice == "Validation state (worst first)":
        filtered.sort(key=lambda r: _VALIDATION_SORT_RANK.get(r["validation_state"], 99))
    elif sort_choice == "Review status (pending first)":
        filtered.sort(key=lambda r: _REVIEW_SORT_RANK.get(r["review_status"], 99))
    else:
        filtered.sort(key=lambda r: r["id"])

    if not filtered:
        st.caption("No requirements match the selected filters.")
        return

    table_rows = [
        {
            "ID": row["id"],
            "Requirement": row["current_text"],
            "Source document": _source_document_label(row),
            "Origin": row["origin"],
            "Model · mode": _summary_provenance_label(row),
            "Validation": (
                f"{VALIDATION_ICONS.get(row['validation_state'], '❔')} "
                f"{row['validation_state'].upper()}"
            ),
            "Review": (
                f"{REVIEW_ICONS.get(row['review_status'], '')} "
                f"{row['review_status'].upper()}"
            ),
            "WARN acknowledged": (
                "—"
                if row["validation_state"] != "warn"
                else ("Yes" if row["warn_acknowledged"] else "No")
            ),
            "AC count": row["acceptance_criteria_count"],
        }
        for row in filtered
    ]
    st.dataframe(table_rows, use_container_width=True, hide_index=True)

    st.markdown("**Inspect a requirement**")
    selectable_ids = [row["id"] for row in filtered]
    selected_id = st.selectbox(
        "Select a requirement ID to review in detail",
        selectable_ids,
        key="audit_summary_selected_requirement",
    )
    if selected_id is not None:
        selected_row = next(row for row in filtered if row["id"] == selected_id)
        render_requirement_card(
            selected_id,
            selected_row["model_name"] or "—",
            selected_row["mode"] or "live",
            scope="audit",
        )


def main() -> None:
    render_header()
    workflow_tab, audit_tab = st.tabs(["Workflow", "Audit & Traceability Summary"])

    with workflow_tab:
        render_input_section()
        render_replay_section()
        render_results_section()

    with audit_tab:
        render_audit_summary_section()


if __name__ == "__main__":
    main()
