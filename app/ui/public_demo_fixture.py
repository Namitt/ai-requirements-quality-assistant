"""Captured public-demo fixture data and loader.

This is a genuine snapshot of output produced by this application's real
workflow, captured on 2026-08-25 via real Google Gemini (gemini-3.5-flash)
Developer API calls made on the developer's own machine - not fabricated.
The capture procedure: run the real FastAPI app against a throwaway
database, POST /extractions for two source documents (one of them
app/ui/demo_fixture.py's existing demo text, unchanged), validate every
resulting requirement with the real deterministic engine, approve/reject/
acknowledge through the real review endpoints, draft one acceptance
criterion through the real AI-drafting endpoint, and replay one of the
live extraction runs through the real replay endpoint - then read the
resulting state back out through the application's own read endpoints.

Nothing here was hand-written to fit a desired PASS/WARN/FAIL table. The
actual distribution this produced - 2 PASS, 4 WARN, 5 FAIL across 11
requirements, 2 approved (one PASS with no acknowledgement needed, one
WARN with an explicit acknowledgement), 1 rejected, 8 left pending, one
acceptance criterion (WARN), one live-mode source document replayed a
second time - is whatever the real engine actually computed against real
AI output; see module2-review-handoff... (n/a) / the fixture-capture
report for the full before/after distribution and why Document 2's text
was revised once to obtain a genuine FAIL case.

Two deliberate normalisations were applied when freezing this snapshot,
neither of which touches any AI-authored or rule-computed content:

- `warn_acknowledged_by`: the real capture recorded the developer's local
  OS username (via `getpass.getuser()`, same as
  `app/api/routes/requirements.py` does for a real analyst action) on the
  one acknowledged WARN row. That username is reviewer metadata, not AI
  output, and has no place in a public artifact - `seed_fixture()`
  substitutes the neutral constant `DEMO_ACKNOWLEDGED_BY` instead.
- Timestamps (`created_at`, `updated_at`, `run_at`, `warn_acknowledged_at`)
  are not carried through at all; `seed_fixture()` lets each row's normal
  database default apply (or stamps "now" for `warn_acknowledged_at`), so
  every public-demo session's seeded data looks freshly created rather
  than increasingly dated the longer the fixture goes unrefreshed.

`FIXTURE` intentionally does not reference any database id: every parent/
child relationship is expressed with a local string `ref`, resolved by
`seed_fixture()` at insert time against whatever ids the target database
actually assigns. This is what makes the fixture safe to seed repeatedly
into a fresh, empty database (as the public demo does, once per Streamlit
session) without any coupling to a specific prior run's autoincrement
values.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import (
    AcceptanceCriterion,
    ExtractedAcceptanceCriterion,
    ExtractedRequirement,
    ExtractionRun,
    Requirement,
    SourceDocument,
    ValidationResult,
    ValidationRule,
    ValidationRun,
)

VALIDATOR_VERSION = "1.0.0"

# Neutral stand-in for the real capture's local OS username - see module
# docstring. Not a real identity; never displayed as though it were AI
# output.
DEMO_ACKNOWLEDGED_BY = "demo-analyst"

# Mirrors the severity ordering already established independently in
# app/validation_engine.py (_SEVERITY_ORDER) and in the multi-sibling
# aggregation rules (app/rules/duplicate_near.py,
# app/rules/possible_contradiction.py) - duplicated here as a small, local,
# self-contained constant rather than importing a private name from a
# frozen module.
_SEVERITY_ORDER = {"pass": 0, "warn": 1, "fail": 2}


FIXTURE = {
    "source_documents": [
        {
            "ref": "doc1",
            "title": "Store manager absence-request process (call notes)",
            "raw_text": "Notes from a call with the regional retail operations lead, discussing how store managers currently handle staff absence requests.\n\nRight now, when someone on the shop floor wants to book time off, they just email their store manager directly, and it's honestly a mess - nothing's tracked centrally, so if a manager goes on leave themselves, requests can just sit in an inbox for weeks. The regional lead wants a way to fix this before the next scheduling cycle.\n\nWhatever we build needs to notify the store manager within 2 hours of an absence request being submitted, so nothing gets missed over a weekend.\n\nShe also wants managers to be able to review requests in some kind of user-friendly way, since some of the current store managers aren't very tech-savvy and the last system the company tried was apparently a nightmare to use.\n\nOn approvals: the system shall allow store managers to approve or reject absence requests submitted by their staff. Actually, thinking about it more, the system shall allow store managers to approve or decline absence requests submitted by their staff - either way, they need the ability to make that call themselves, we don't want head office approving on their behalf.\n",
        },
        {
            "ref": "doc2",
            "title": "Helpdesk ticket escalation process (stakeholder notes)",
            "raw_text": "Notes from a workshop with the customer support lead about how urgent tickets get escalated today. Right now, when a ticket sits unanswered for too long, agents just message a team lead directly on chat — there's no consistent rule for what counts as 'too long'. The support lead wants the system to automatically escalate a ticket to a team lead if it has not received a first response within 4 business hours. She also wants the system to notify the original customer in a reasonably prompt way once their ticket has been escalated. Finally, agents should be able to manually escalate any ticket themselves at any time, if they judge it needs senior attention sooner. Agents shall be able to add an internal note to any ticket before escalating it. Agents shall be able to add an internal note to any ticket before it is escalated.",
        },
    ],
    "extraction_runs": [
        {
            "ref": "run1",
            "source_document_ref": "doc1",
            "model_name": "gemini-3.5-flash",
            "prompt_version": "1.0.0",
            "mode": "live",
            "replayed_from_ref": None,
            "extracted_requirements": [
                {
                    "requirement_text": "The system shall notify the store manager within 2 hours of an absence request being submitted.",
                    "source_quote": "Whatever we build needs to notify the store manager within 2 hours of an absence request being submitted",
                    "source_span_start": 464,
                    "source_span_end": 568,
                    "requirement": {
                        "current_text": "The system shall notify the store manager within 2 hours of an absence request being submitted.",
                        "origin": "ai_generated",
                        "review_status": "approved",
                        "warn_acknowledged": False,
                        "validation_results": [
                            {
                                "rule_code": "DUPLICATE_NEAR",
                                "result": "pass",
                                "message": "No near-duplicate found. Closest match: requirement #3 at similarity 0.64.",
                                "recommended_action": None,
                            },
                            {
                                "rule_code": "AMBIGUOUS_WORDING",
                                "result": "pass",
                                "message": "No ambiguous terms found.",
                                "recommended_action": None,
                            },
                            {
                                "rule_code": "MISSING_ACCEPTANCE_CONDITION",
                                "result": "pass",
                                "message": "A measurable or testable acceptance condition was found.",
                                "recommended_action": None,
                            },
                            {
                                "rule_code": "MISSING_ACTOR",
                                "result": "pass",
                                "message": "An actor was identified in the requirement text.",
                                "recommended_action": None,
                            },
                            {
                                "rule_code": "POSSIBLE_CONTRADICTION",
                                "result": "pass",
                                "message": "No possible contradiction found within the comparison scope.",
                                "recommended_action": None,
                            },
                        ],
                        "acceptance_criteria": [
                            {
                                "criterion_text": "Given an employee has submitted an absence request, when 2 hours have elapsed since the submission, then the store manager must have received a notification of the request.",
                                "mode": "live",
                                "model_name": "gemini-3.5-flash",
                                "prompt_version": "1.0.0",
                                "review_status": "pending",
                                "warn_acknowledged": False,
                                "validation_results": [
                                    {
                                        "rule_code": "AC_GIVEN_PRESENT",
                                        "result": "pass",
                                        "message": "A Given clause was found.",
                                        "recommended_action": None,
                                    },
                                    {
                                        "rule_code": "AC_WHEN_PRESENT",
                                        "result": "pass",
                                        "message": "A When clause was found.",
                                        "recommended_action": None,
                                    },
                                    {
                                        "rule_code": "AC_THEN_PRESENT",
                                        "result": "pass",
                                        "message": "A Then clause was found.",
                                        "recommended_action": None,
                                    },
                                    {
                                        "rule_code": "AC_MEASURABLE_THEN",
                                        "result": "warn",
                                        "message": "No measurable or testable condition was found in the Then clause.",
                                        "recommended_action": "Add a measurable condition (a number, threshold phrase, or conditional connector) to the Then clause.",
                                    },
                                ],
                            },
                        ],
                    },
                },
                {
                    "requirement_text": "The system shall provide a user-friendly way for store managers to review absence requests.",
                    "source_quote": "She also wants managers to be able to review requests in some kind of user-friendly way",
                    "source_span_start": 610,
                    "source_span_end": 697,
                    "requirement": {
                        "current_text": "The system shall provide a user-friendly way for store managers to review absence requests.",
                        "origin": "ai_generated",
                        "review_status": "approved",
                        "warn_acknowledged": True,
                        "validation_results": [
                            {
                                "rule_code": "DUPLICATE_NEAR",
                                "result": "pass",
                                "message": "No near-duplicate found. Closest match: requirement #1 at similarity 0.62.",
                                "recommended_action": None,
                            },
                            {
                                "rule_code": "AMBIGUOUS_WORDING",
                                "result": "warn",
                                "message": "Ambiguous term(s) found: user-friendly.",
                                "recommended_action": "Rewrite with a measurable criterion if genuinely vague; otherwise dismiss with acknowledgement.",
                            },
                            {
                                "rule_code": "MISSING_ACCEPTANCE_CONDITION",
                                "result": "warn",
                                "message": "No measurable or testable acceptance condition was found.",
                                "recommended_action": "Add a measurable condition if this requirement is meant to be delivery-ready, or approve as-is if it is intentionally a high-level statement awaiting decomposition.",
                            },
                            {
                                "rule_code": "MISSING_ACTOR",
                                "result": "pass",
                                "message": "An actor was identified in the requirement text.",
                                "recommended_action": None,
                            },
                            {
                                "rule_code": "POSSIBLE_CONTRADICTION",
                                "result": "pass",
                                "message": "No possible contradiction found within the comparison scope.",
                                "recommended_action": None,
                            },
                        ],
                        "acceptance_criteria": [],
                    },
                },
                {
                    "requirement_text": "The system shall allow store managers to approve or decline absence requests submitted by their staff.",
                    "source_quote": "the system shall allow store managers to approve or decline absence requests submitted by their staff",
                    "source_span_start": 987,
                    "source_span_end": 1088,
                    "requirement": {
                        "current_text": "The system shall allow store managers to approve or decline absence requests submitted by their staff.",
                        "origin": "ai_generated",
                        "review_status": "pending",
                        "warn_acknowledged": False,
                        "validation_results": [
                            {
                                "rule_code": "DUPLICATE_NEAR",
                                "result": "pass",
                                "message": "No near-duplicate found. Closest match: requirement #1 at similarity 0.66.",
                                "recommended_action": None,
                            },
                            {
                                "rule_code": "AMBIGUOUS_WORDING",
                                "result": "pass",
                                "message": "No ambiguous terms found.",
                                "recommended_action": None,
                            },
                            {
                                "rule_code": "MISSING_ACCEPTANCE_CONDITION",
                                "result": "warn",
                                "message": "No measurable or testable acceptance condition was found.",
                                "recommended_action": "Add a measurable condition if this requirement is meant to be delivery-ready, or approve as-is if it is intentionally a high-level statement awaiting decomposition.",
                            },
                            {
                                "rule_code": "MISSING_ACTOR",
                                "result": "pass",
                                "message": "An actor was identified in the requirement text.",
                                "recommended_action": None,
                            },
                            {
                                "rule_code": "POSSIBLE_CONTRADICTION",
                                "result": "pass",
                                "message": "No possible contradiction found within the comparison scope.",
                                "recommended_action": None,
                            },
                        ],
                        "acceptance_criteria": [],
                    },
                },
            ],
        },
        {
            "ref": "run2",
            "source_document_ref": "doc2",
            "model_name": "gemini-3.5-flash",
            "prompt_version": "1.0.0",
            "mode": "live",
            "replayed_from_ref": None,
            "extracted_requirements": [
                {
                    "requirement_text": "The system shall automatically escalate a ticket to a team lead if the ticket has not received a first response within 4 business hours.",
                    "source_quote": "The support lead wants the system to automatically escalate a ticket to a team lead if it has not received a first response within 4 business hours.",
                    "source_span_start": 263,
                    "source_span_end": 411,
                    "requirement": {
                        "current_text": "The system shall automatically escalate a ticket to a team lead if the ticket has not received a first response within 4 business hours.",
                        "origin": "ai_generated",
                        "review_status": "pending",
                        "warn_acknowledged": False,
                        "validation_results": [
                            {
                                "rule_code": "DUPLICATE_NEAR",
                                "result": "pass",
                                "message": "No near-duplicate found. Closest match: requirement #6 at similarity 0.50.",
                                "recommended_action": None,
                            },
                            {
                                "rule_code": "AMBIGUOUS_WORDING",
                                "result": "pass",
                                "message": "No ambiguous terms found.",
                                "recommended_action": None,
                            },
                            {
                                "rule_code": "MISSING_ACCEPTANCE_CONDITION",
                                "result": "pass",
                                "message": "A measurable or testable acceptance condition was found.",
                                "recommended_action": None,
                            },
                            {
                                "rule_code": "MISSING_ACTOR",
                                "result": "pass",
                                "message": "An actor was identified in the requirement text.",
                                "recommended_action": None,
                            },
                            {
                                "rule_code": "POSSIBLE_CONTRADICTION",
                                "result": "pass",
                                "message": "No possible contradiction found within the comparison scope.",
                                "recommended_action": None,
                            },
                        ],
                        "acceptance_criteria": [],
                    },
                },
                {
                    "requirement_text": "The system shall notify the original customer once their ticket has been escalated.",
                    "source_quote": "She also wants the system to notify the original customer in a reasonably prompt way once their ticket has been escalated.",
                    "source_span_start": 412,
                    "source_span_end": 534,
                    "requirement": {
                        "current_text": "The system shall notify the original customer once their ticket has been escalated.",
                        "origin": "ai_generated",
                        "review_status": "pending",
                        "warn_acknowledged": False,
                        "validation_results": [
                            {
                                "rule_code": "DUPLICATE_NEAR",
                                "result": "pass",
                                "message": "No near-duplicate found. Closest match: requirement #8 at similarity 0.60.",
                                "recommended_action": None,
                            },
                            {
                                "rule_code": "AMBIGUOUS_WORDING",
                                "result": "pass",
                                "message": "No ambiguous terms found.",
                                "recommended_action": None,
                            },
                            {
                                "rule_code": "MISSING_ACCEPTANCE_CONDITION",
                                "result": "warn",
                                "message": "No measurable or testable acceptance condition was found.",
                                "recommended_action": "Add a measurable condition if this requirement is meant to be delivery-ready, or approve as-is if it is intentionally a high-level statement awaiting decomposition.",
                            },
                            {
                                "rule_code": "MISSING_ACTOR",
                                "result": "pass",
                                "message": "An actor was identified in the requirement text.",
                                "recommended_action": None,
                            },
                            {
                                "rule_code": "POSSIBLE_CONTRADICTION",
                                "result": "pass",
                                "message": "No possible contradiction found within the comparison scope.",
                                "recommended_action": None,
                            },
                        ],
                        "acceptance_criteria": [],
                    },
                },
                {
                    "requirement_text": "The system shall allow agents to manually escalate any ticket at any time.",
                    "source_quote": "Finally, agents should be able to manually escalate any ticket themselves at any time, if they judge it needs senior attention sooner.",
                    "source_span_start": 535,
                    "source_span_end": 669,
                    "requirement": {
                        "current_text": "The system shall allow agents to manually escalate any ticket at any time.",
                        "origin": "ai_generated",
                        "review_status": "pending",
                        "warn_acknowledged": False,
                        "validation_results": [
                            {
                                "rule_code": "DUPLICATE_NEAR",
                                "result": "pass",
                                "message": "No near-duplicate found. Closest match: requirement #7 at similarity 0.70.",
                                "recommended_action": None,
                            },
                            {
                                "rule_code": "AMBIGUOUS_WORDING",
                                "result": "pass",
                                "message": "No ambiguous terms found.",
                                "recommended_action": None,
                            },
                            {
                                "rule_code": "MISSING_ACCEPTANCE_CONDITION",
                                "result": "warn",
                                "message": "No measurable or testable acceptance condition was found.",
                                "recommended_action": "Add a measurable condition if this requirement is meant to be delivery-ready, or approve as-is if it is intentionally a high-level statement awaiting decomposition.",
                            },
                            {
                                "rule_code": "MISSING_ACTOR",
                                "result": "pass",
                                "message": "An actor was identified in the requirement text.",
                                "recommended_action": None,
                            },
                            {
                                "rule_code": "POSSIBLE_CONTRADICTION",
                                "result": "pass",
                                "message": "No possible contradiction found within the comparison scope.",
                                "recommended_action": None,
                            },
                        ],
                        "acceptance_criteria": [],
                    },
                },
                {
                    "requirement_text": "The system shall allow agents to add an internal note to any ticket before escalating it.",
                    "source_quote": "Agents shall be able to add an internal note to any ticket before escalating it.",
                    "source_span_start": 670,
                    "source_span_end": 750,
                    "requirement": {
                        "current_text": "The system shall allow agents to add an internal note to any ticket before escalating it.",
                        "origin": "ai_generated",
                        "review_status": "pending",
                        "warn_acknowledged": False,
                        "validation_results": [
                            {
                                "rule_code": "DUPLICATE_NEAR",
                                "result": "fail",
                                "message": "Near-exact duplicate of requirement #8 (similarity 0.92).",
                                "recommended_action": "Decide which requirement is canonical and reject or merge the other.",
                            },
                            {
                                "rule_code": "AMBIGUOUS_WORDING",
                                "result": "pass",
                                "message": "No ambiguous terms found.",
                                "recommended_action": None,
                            },
                            {
                                "rule_code": "MISSING_ACCEPTANCE_CONDITION",
                                "result": "warn",
                                "message": "No measurable or testable acceptance condition was found.",
                                "recommended_action": "Add a measurable condition if this requirement is meant to be delivery-ready, or approve as-is if it is intentionally a high-level statement awaiting decomposition.",
                            },
                            {
                                "rule_code": "MISSING_ACTOR",
                                "result": "pass",
                                "message": "An actor was identified in the requirement text.",
                                "recommended_action": None,
                            },
                            {
                                "rule_code": "POSSIBLE_CONTRADICTION",
                                "result": "pass",
                                "message": "No possible contradiction found within the comparison scope.",
                                "recommended_action": None,
                            },
                        ],
                        "acceptance_criteria": [],
                    },
                },
                {
                    "requirement_text": "The system shall allow agents to add an internal note to any ticket before it is escalated.",
                    "source_quote": "Agents shall be able to add an internal note to any ticket before it is escalated.",
                    "source_span_start": 751,
                    "source_span_end": 833,
                    "requirement": {
                        "current_text": "The system shall allow agents to add an internal note to any ticket before it is escalated.",
                        "origin": "ai_generated",
                        "review_status": "rejected",
                        "warn_acknowledged": False,
                        "validation_results": [
                            {
                                "rule_code": "DUPLICATE_NEAR",
                                "result": "fail",
                                "message": "Near-exact duplicate of requirement #7 (similarity 0.92).",
                                "recommended_action": "Decide which requirement is canonical and reject or merge the other.",
                            },
                            {
                                "rule_code": "AMBIGUOUS_WORDING",
                                "result": "pass",
                                "message": "No ambiguous terms found.",
                                "recommended_action": None,
                            },
                            {
                                "rule_code": "MISSING_ACCEPTANCE_CONDITION",
                                "result": "warn",
                                "message": "No measurable or testable acceptance condition was found.",
                                "recommended_action": "Add a measurable condition if this requirement is meant to be delivery-ready, or approve as-is if it is intentionally a high-level statement awaiting decomposition.",
                            },
                            {
                                "rule_code": "MISSING_ACTOR",
                                "result": "pass",
                                "message": "An actor was identified in the requirement text.",
                                "recommended_action": None,
                            },
                            {
                                "rule_code": "POSSIBLE_CONTRADICTION",
                                "result": "pass",
                                "message": "No possible contradiction found within the comparison scope.",
                                "recommended_action": None,
                            },
                        ],
                        "acceptance_criteria": [],
                    },
                },
            ],
        },
        {
            "ref": "run3",
            "source_document_ref": "doc1",
            "model_name": "gemini-3.5-flash",
            "prompt_version": "1.0.0",
            "mode": "replay",
            "replayed_from_ref": "run1",
            "extracted_requirements": [
                {
                    "requirement_text": "The system shall notify the store manager within 2 hours of an absence request being submitted.",
                    "source_quote": "Whatever we build needs to notify the store manager within 2 hours of an absence request being submitted",
                    "source_span_start": 464,
                    "source_span_end": 568,
                    "requirement": {
                        "current_text": "The system shall notify the store manager within 2 hours of an absence request being submitted.",
                        "origin": "ai_generated",
                        "review_status": "pending",
                        "warn_acknowledged": False,
                        "validation_results": [
                            {
                                "rule_code": "DUPLICATE_NEAR",
                                "result": "fail",
                                "message": "Near-exact duplicate of requirement #1 (similarity 1.00).",
                                "recommended_action": "Decide which requirement is canonical and reject or merge the other.",
                            },
                            {
                                "rule_code": "AMBIGUOUS_WORDING",
                                "result": "pass",
                                "message": "No ambiguous terms found.",
                                "recommended_action": None,
                            },
                            {
                                "rule_code": "MISSING_ACCEPTANCE_CONDITION",
                                "result": "pass",
                                "message": "A measurable or testable acceptance condition was found.",
                                "recommended_action": None,
                            },
                            {
                                "rule_code": "MISSING_ACTOR",
                                "result": "pass",
                                "message": "An actor was identified in the requirement text.",
                                "recommended_action": None,
                            },
                            {
                                "rule_code": "POSSIBLE_CONTRADICTION",
                                "result": "pass",
                                "message": "No possible contradiction found within the comparison scope.",
                                "recommended_action": None,
                            },
                        ],
                        "acceptance_criteria": [],
                    },
                },
                {
                    "requirement_text": "The system shall provide a user-friendly way for store managers to review absence requests.",
                    "source_quote": "She also wants managers to be able to review requests in some kind of user-friendly way",
                    "source_span_start": 610,
                    "source_span_end": 697,
                    "requirement": {
                        "current_text": "The system shall provide a user-friendly way for store managers to review absence requests.",
                        "origin": "ai_generated",
                        "review_status": "pending",
                        "warn_acknowledged": False,
                        "validation_results": [
                            {
                                "rule_code": "DUPLICATE_NEAR",
                                "result": "fail",
                                "message": "Near-exact duplicate of requirement #2 (similarity 1.00).",
                                "recommended_action": "Decide which requirement is canonical and reject or merge the other.",
                            },
                            {
                                "rule_code": "AMBIGUOUS_WORDING",
                                "result": "warn",
                                "message": "Ambiguous term(s) found: user-friendly.",
                                "recommended_action": "Rewrite with a measurable criterion if genuinely vague; otherwise dismiss with acknowledgement.",
                            },
                            {
                                "rule_code": "MISSING_ACCEPTANCE_CONDITION",
                                "result": "warn",
                                "message": "No measurable or testable acceptance condition was found.",
                                "recommended_action": "Add a measurable condition if this requirement is meant to be delivery-ready, or approve as-is if it is intentionally a high-level statement awaiting decomposition.",
                            },
                            {
                                "rule_code": "MISSING_ACTOR",
                                "result": "pass",
                                "message": "An actor was identified in the requirement text.",
                                "recommended_action": None,
                            },
                            {
                                "rule_code": "POSSIBLE_CONTRADICTION",
                                "result": "pass",
                                "message": "No possible contradiction found within the comparison scope.",
                                "recommended_action": None,
                            },
                        ],
                        "acceptance_criteria": [],
                    },
                },
                {
                    "requirement_text": "The system shall allow store managers to approve or decline absence requests submitted by their staff.",
                    "source_quote": "the system shall allow store managers to approve or decline absence requests submitted by their staff",
                    "source_span_start": 987,
                    "source_span_end": 1088,
                    "requirement": {
                        "current_text": "The system shall allow store managers to approve or decline absence requests submitted by their staff.",
                        "origin": "ai_generated",
                        "review_status": "pending",
                        "warn_acknowledged": False,
                        "validation_results": [
                            {
                                "rule_code": "DUPLICATE_NEAR",
                                "result": "fail",
                                "message": "Near-exact duplicate of requirement #3 (similarity 1.00).",
                                "recommended_action": "Decide which requirement is canonical and reject or merge the other.",
                            },
                            {
                                "rule_code": "AMBIGUOUS_WORDING",
                                "result": "pass",
                                "message": "No ambiguous terms found.",
                                "recommended_action": None,
                            },
                            {
                                "rule_code": "MISSING_ACCEPTANCE_CONDITION",
                                "result": "warn",
                                "message": "No measurable or testable acceptance condition was found.",
                                "recommended_action": "Add a measurable condition if this requirement is meant to be delivery-ready, or approve as-is if it is intentionally a high-level statement awaiting decomposition.",
                            },
                            {
                                "rule_code": "MISSING_ACTOR",
                                "result": "pass",
                                "message": "An actor was identified in the requirement text.",
                                "recommended_action": None,
                            },
                            {
                                "rule_code": "POSSIBLE_CONTRADICTION",
                                "result": "pass",
                                "message": "No possible contradiction found within the comparison scope.",
                                "recommended_action": None,
                            },
                        ],
                        "acceptance_criteria": [],
                    },
                },
            ],
        },
    ],
}


def seed_fixture(session: Session) -> dict[str, int]:
    """Insert FIXTURE into `session`'s database, in dependency order.

    Assumes the schema already exists and `validation_rules` is already
    seeded (e.g. via app.seed.seed_validation_rules) - this function only
    resolves rule codes to the ids that seeding produced; it does not seed
    the catalog itself.

    Every row is inserted as `review_status='pending'` first (the state
    every real extraction/draft actually starts in) and only updated to
    its final approved/rejected state, with warn_acknowledged_at/by set,
    after validation has been seeded and validation_state is already
    correct - mirroring the real application's own create -> validate ->
    approve/reject call sequence, and avoiding ever writing a row that
    would (even momentarily) violate the approval-gating CHECK
    constraints on `requirements`/`acceptance_criteria`.

    Returns a mapping of every `ref` used in FIXTURE to the real database
    id it was assigned, for callers that need to point the UI at a
    specific seeded row (e.g. which extraction run to show by default).
    """
    rule_id_by_code = {
        code: rule_id
        for code, rule_id in session.query(ValidationRule.code, ValidationRule.id).all()
    }

    refs: dict[str, int] = {}

    for doc in FIXTURE["source_documents"]:
        row = SourceDocument(title=doc["title"], raw_text=doc["raw_text"])
        session.add(row)
        session.flush()
        refs[doc["ref"]] = row.id

    for run in FIXTURE["extraction_runs"]:
        replayed_from_run_id = (
            refs[run["replayed_from_ref"]] if run["replayed_from_ref"] else None
        )
        run_row = ExtractionRun(
            source_document_id=refs[run["source_document_ref"]],
            model_name=run["model_name"],
            prompt_version=run["prompt_version"],
            mode=run["mode"],
            replayed_from_run_id=replayed_from_run_id,
        )
        session.add(run_row)
        session.flush()
        refs[run["ref"]] = run_row.id

        for extracted_entry in run["extracted_requirements"]:
            extracted_row = ExtractedRequirement(
                extraction_run_id=run_row.id,
                requirement_text=extracted_entry["requirement_text"],
                source_span_start=extracted_entry["source_span_start"],
                source_span_end=extracted_entry["source_span_end"],
                source_quote=extracted_entry["source_quote"],
            )
            session.add(extracted_row)
            session.flush()

            req_data = extracted_entry["requirement"]
            requirement_row = Requirement(
                source_extraction_id=extracted_row.id,
                current_text=req_data["current_text"],
                origin=req_data["origin"],
                review_status="pending",
            )
            session.add(requirement_row)
            session.flush()

            requirement_row.validation_state = _seed_validation_results(
                session,
                rule_id_by_code,
                requirement_id=requirement_row.id,
                acceptance_criterion_id=None,
                results=req_data["validation_results"],
            )
            if req_data["warn_acknowledged"]:
                requirement_row.warn_acknowledged_at = datetime.now(timezone.utc)
                requirement_row.warn_acknowledged_by = DEMO_ACKNOWLEDGED_BY
            requirement_row.review_status = req_data["review_status"]
            session.flush()

            for ac_data in req_data["acceptance_criteria"]:
                extracted_ac_row = ExtractedAcceptanceCriterion(
                    requirement_id=requirement_row.id,
                    criterion_text=ac_data["criterion_text"],
                    mode=ac_data["mode"],
                    replayed_from_id=None,
                    model_name=ac_data["model_name"],
                    prompt_version=ac_data["prompt_version"],
                )
                session.add(extracted_ac_row)
                session.flush()

                ac_row = AcceptanceCriterion(
                    source_extraction_id=extracted_ac_row.id,
                    current_text=ac_data["criterion_text"],
                    review_status="pending",
                )
                session.add(ac_row)
                session.flush()

                ac_row.validation_state = _seed_validation_results(
                    session,
                    rule_id_by_code,
                    requirement_id=None,
                    acceptance_criterion_id=ac_row.id,
                    results=ac_data["validation_results"],
                )
                if ac_data["warn_acknowledged"]:
                    ac_row.warn_acknowledged_at = datetime.now(timezone.utc)
                    ac_row.warn_acknowledged_by = DEMO_ACKNOWLEDGED_BY
                ac_row.review_status = ac_data["review_status"]
                session.flush()

    session.commit()
    return refs


def _seed_validation_results(
    session: Session,
    rule_id_by_code: dict[str, int],
    *,
    requirement_id: int | None,
    acceptance_criterion_id: int | None,
    results: list[dict],
) -> str:
    """Inserts one frozen ValidationRun + its ValidationResult rows: the
    exact captured rule_code/result/message/recommended_action from the
    real capture, not recomputed. Returns the worst-of-N result, which the
    caller stores as the parent row's validation_state.
    """
    run_row = ValidationRun(
        requirement_id=requirement_id,
        acceptance_criterion_id=acceptance_criterion_id,
        validator_version=VALIDATOR_VERSION,
    )
    session.add(run_row)
    session.flush()

    for result in results:
        session.add(
            ValidationResult(
                validation_run_id=run_row.id,
                rule_id=rule_id_by_code[result["rule_code"]],
                result=result["result"],
                message=result["message"],
                recommended_action=result["recommended_action"],
            )
        )
    session.flush()

    return max((r["result"] for r in results), key=lambda r: _SEVERITY_ORDER[r])
