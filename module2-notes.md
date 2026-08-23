# Module 2 Notes — Acceptance Criteria Assistant

Interview-preparation notes for Module 2 of the AI Requirements &
Traceability Workbench. Module 2 extends Module 1's requirements
workflow with AI-drafted, deterministically checked Given/When/Then
acceptance criteria. Module 1's own notes remain in `module1-notes.md`.

## What Module 2 does

For any existing requirement — pending, approved, or rejected — the
analyst can ask AI to draft a single Given/When/Then acceptance
criterion. That draft is stored, automatically checked by four fixed
structural rules, and then reviewed by the analyst exactly like a
requirement: edit, approve, or reject. An acceptance criterion has its
own independent lifecycle — approving or rejecting one never changes
the parent requirement's own status. The pipeline is the same shape as
Module 1's: AI drafts → deterministic rules check → human decides.

## What the AI does

The AI drafts exactly one acceptance criterion from a requirement's
current text, in Given/When/Then form. It reuses the same
`ExtractionClient` abstraction Module 1's extraction uses — no new AI
client was built. As with Module 1, the AI never checks its own work,
never approves anything, and is never presented as having judged the
criterion correct.

## What the deterministic validator does

Four fixed rules run against every acceptance criterion: is a Given
clause present, is a When clause present, is a Then clause present,
and does the Then clause contain a measurable or testable condition
(reusing the exact same number/threshold/conditional regex signals
Module 1's `MISSING_ACCEPTANCE_CONDITION` rule already uses). All four
are WARN-only in this version — applying the same confidence ×
significance framework Module 1 established, none of these keyword
checks is confident enough to justify blocking approval outright, the
same reasoning that keeps four of Module 1's five rules WARN-only.
The FAIL-blocking gate is still fully built and tested; it's simply
never triggered by the current four rules.

These four rules share the exact same `validation_rules`,
`validation_runs`, and `validation_results` tables Module 1's five
rules use, rather than a second, parallel validation subsystem. The
one schema change this required was widening `validation_runs` to
have two nullable parent columns (`requirement_id`,
`acceptance_criterion_id`) with a database constraint guaranteeing
exactly one is ever set — `app/validation_engine.py` itself needed no
code changes at all to support this, and a dedicated regression test
proves requirement validation still produces exactly five results,
unchanged.

## What the human does

The analyst reviews each drafted criterion — its text, its four
structural results, and its edit history — and edits, approves, or
rejects it. WARN requires an explicit acknowledgement (who, when)
before approval, cleared automatically by any further edit, identical
to Module 1's requirement workflow. Approving or rejecting a criterion
never touches the parent requirement's `review_status` — this was
verified both by direct engine tests and by API-level tests that
create, approve, and reject criteria and assert the parent
requirement is untouched throughout.

## What happens when an acceptance criterion is edited

Exactly the same pattern as a requirement edit: the previous and new
text are recorded in `acceptance_criteria_edits` (never overwritten),
the criterion is re-validated automatically, and any existing WARN
acknowledgement is cleared so a stale acknowledgement can never cover
a validation result the analyst hasn't actually seen.

## Replay, for acceptance criteria

Module 1's replay mode re-runs a previously captured live extraction
run; Module 2 applies the same principle at the level of a single
criterion. A live draft is recorded on `extracted_acceptance_criteria`
with `mode='live'`; replaying it creates a fresh
`extracted_acceptance_criteria` row (`mode='replay'`,
`replayed_from_id` pointing at the original) and a fresh reviewable
criterion, run through the identical validation/review pipeline, with
no AI call made. A replay can never itself be replayed. Unlike Module
1, there is no run/batch table behind this — because one live request
always drafts exactly one criterion, there was nothing for a separate
run table to group, so live/replay tracking lives directly on the
extracted-criterion record itself. This is a real, evidenced
architectural difference from Module 1's replay design, not an
oversight — see the decisions-log entry for the full reasoning.

## Traceability

Every acceptance criterion resolves to: the requirement it was drafted
for, that requirement's own extracted evidence and source document (if
it has one), and the model/prompt version used to draft the criterion
itself. This chain stays within a single requirement — there is no
cross-requirement or cross-document comparison for acceptance criteria,
unlike `DUPLICATE_NEAR`/`POSSIBLE_CONTRADICTION` for requirements.

## What was difficult / genuinely unclear

Reusing `validation_runs`/`validation_results` for a second entity
type without touching the frozen `app/validation_engine.py` was the
central design problem. The fix was a nullable dual-foreign-key column
pair with a database-level "exactly one parent" constraint, plus a
completely separate dispatch function
(`app/acceptance_criteria_validation_engine.py`) with its own
hardcoded rule-code list — so the two validators can never accidentally
run each other's rules, and the shared tables never need to know which
kind of entity a given row belongs to beyond which foreign key is set.
A dedicated regression test — running the original `run_validation()`
after the four new rule rows exist in the catalog — proves this holds:
still exactly five results, still the original five rule codes.

## How it was tested

96 new automated tests were added: 24 schema-level tests (both new
`CHECK` constraint pairs, the four approval constraints on
`acceptance_criteria`, and all four combinations of the new
`validation_runs` exactly-one-parent constraint), 20 engine tests
(drafting, metadata, all three parent-requirement review statuses,
replay, replay-of-replay rejection, no-AI-call-on-replay), 15
validation-engine tests (each rule independently, aggregation,
atomicity, and the requirement-validation regression test above), 30
API tests (the full draft/list/get/replay/edit/approve/reject/review
workflow, including the parent-requirement-untouched assertions), and
7 UI api-client tests. All 214 pre-existing tests continue to pass
unchanged — 310 total, 0 failures.

## How I would explain Module 2 in an interview

"Module 2 asks: once AI has helped draft a requirement and a human has
reviewed it, can the same pattern help with the next artifact a BA
actually needs — acceptance criteria? I reused the exact same
AI-drafts / deterministic-rules-check / human-decides shape, but
proved the architecture actually generalizes rather than just copying
it: the same validation tables now serve two independent rule
dispatchers without either one being able to affect the other, which I
verified with a regression test, not just an assumption. The
acceptance criterion has its own approval lifecycle completely
separate from the requirement it came from — approving one is never
allowed to quietly approve or change the other, which matters because
in a real BA workflow those are genuinely two different decisions made
at different times, sometimes by different confidence levels of
review."
