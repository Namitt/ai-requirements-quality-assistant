# Decisions Log

This log records material project decisions: architecture, data
modelling, validation rules, AI behaviour, technology choices,
UX/workflow, scope, rejected alternatives, and significant
implementation trade-offs. It does not record routine implementation
detail.

---

## 2026-08-22 — Technology stack

**Decision:** Python + FastAPI backend, SQLite via SQLAlchemy, React +
Vite frontend (deliberately small), pytest for testing, Anthropic API
for extraction.

**Context:** Needed a stack that is credible for a BA/DA portfolio
project, fast to build, and easy to explain and defend in an
interview.

**Options considered:**
- Backend: FastAPI vs. Node/Express.
- Frontend: React + Vite vs. server-rendered HTML (Jinja2/HTMX) vs.
  Streamlit.
- AI provider: Anthropic API vs. OpenAI API.

**Decision made:** Python/FastAPI, React + Vite (kept intentionally
small), SQLite/SQLAlchemy, pytest, Anthropic API.

**Reason:** Python keeps AI-handling and data-handling code in one
language appropriate to a BA/DA context. A small React SPA reads as a
genuine working application in an interview without becoming a
frontend-engineering exercise, which is explicitly not the point of
this project. SQLite/SQLAlchemy gives explicit relational structure at
a scale that needs no server process.

**Trade-offs:** React + Vite costs more build time than Streamlit
would have. The frontend is capped deliberately small so that cost
does not compound into scope creep.

**Impact:** Sets the technical shape of every later module.

---

## 2026-08-22 — Relational data model, not a graph database

**Decision:** Use SQLite with explicit relational tables and foreign
keys; do not introduce a graph database.

**Context:** The project involves traceability chains (source →
extraction → requirement → validation → edits) that could tempt a
graph-modelling approach.

**Options considered:** Relational (SQLite) vs. graph database.

**Decision made:** Relational.

**Reason:** Every relationship in this system is a simple one-to-many
chain. There is no variable-depth traversal or arbitrary relationship
typing that would justify a graph model's added complexity.

**Trade-offs:** None significant at this scale; a graph database would
have added operational overhead with no corresponding benefit.

**Impact:** Confirms SQLite/SQLAlchemy as sufficient for this
project's intended scope. This is a scoped judgement about this
project's relationships and data volume, not a general claim that
SQLite is superior for other systems or larger-scale needs.

---

## 2026-08-22 — Two-table model for AI output vs. reviewed requirement

**Decision:** Separate `extracted_requirements` (immutable AI output)
from `requirements` (mutable, reviewable, approvable entity). A
`requirements` row is created automatically for every
`extracted_requirements` row at extraction time. The original AI
output is preserved unchanged even if the paired requirement is later
edited, rejected, merged, or replaced.

**Context:** Needed a clear conceptual and structural distinction
between what the AI produced and what the business requirement
actually is after human review, without adding a manual "promotion"
step that the demo does not need.

**Options considered:**
1. Single merged table (extraction writes directly into a status-
   tracked requirements table).
2. Two tables with a manual promotion step (staging/inbox model).
3. Two tables, automatically paired at extraction time (chosen).

**Decision made:** Option 3.

**Reason:** Validation needs to run on AI output immediately, before
any human action — this is central to the demo. A manual promotion
step (option 2) would delay that or force duplicated validation logic.
A single table (option 1) would lose a clean, immutable record of
exactly what the AI originally produced once edits happen in place.
Automatic pairing keeps `extracted_requirements` as a pure audit log
and `requirements` as the single place validation, review, and
approval happen.

**Trade-offs:** Every extraction writes two rows instead of one, and
the schema has one more table than the simplest option. In exchange,
"what the AI said" and "what the requirement now is" can always be
diffed cleanly, including after rejection, merging, or a candidate
being split into multiple requirements.

**Impact:** Defines the core schema and the traceability model for the
rest of the project.

---

## 2026-08-22 — Three orthogonal lifecycle fields, not one status field

**Decision:** `requirements` uses three independent fields — `origin`,
`validation_state`, `review_status` — instead of one combined status
enum. Edited status is derived from `requirement_edits`, not stored as
a redundant field.

**Context:** A single status field mixing AI/human origin, validation
outcome, and approval decision would need compound values (e.g.
"ai_generated_warn_approved") to represent real combinations.

**Options considered:**
1. Single overloaded status enum.
2. Three orthogonal fields (chosen).

**Decision made:** Option 2.

**Reason:** Origin, validation outcome, and human decision are
independent facts — a requirement can be AI-origin, currently WARN,
and approved, all at once. Separate fields make this representable
without compound enum values, and make the audit/summary view a
simple cross-tab of the three fields.

**Trade-offs:** Three columns instead of one, but each is
independently simple and each is unambiguous on its own.

**Impact:** Shapes the requirements table schema and the summary/audit
view design.

---

## 2026-08-22 — Deterministic-only validation

**Decision:** All validation rules are deterministic pattern/structure
checks. No rule calls an AI model to judge requirement quality or
correctness.

**Context:** Needed to decide whether validation itself could use an
LLM (e.g. "ask the model if this requirement is good").

**Options considered:** Deterministic rule engine vs. LLM-based
validation vs. a hybrid.

**Decision made:** Deterministic only.

**Reason:** The project's core claim is a clear separation between
AI-generated content and validated content. An LLM-based validator
would blur that line and produce results that cannot be traced to a
specific, inspectable rule the way a pattern check can.

**Trade-offs:** Deterministic rules cannot catch semantic issues (e.g.
paraphrased duplicates, true contradictions) that a model-based check
might catch. This trade-off is accepted and documented in
`limitations.md` rather than hidden.

**Impact:** Defines the validation engine architecture and directly
shapes the five validation rules.

---

## 2026-08-22 — Replay mode is database-backed, no separate cache/fixture system

**Decision:** Replay mode creates a new `extraction_runs` row
(`mode='replay'`) referencing the original run via
`replayed_from_run_id`, copies the original run's extracted
requirements into fresh rows, and runs them through the identical
validation/review/approval pipeline. No live API call is made. No
separate cache layer or fixture-file system is introduced;
`raw_response` is stored on `extraction_runs` for live runs.

**Context:** The demo must remain usable if the API, network, or API
key is unavailable during an interview.

**Options considered:**
1. Read-only replay of the original run's data (no new rows).
2. Database-backed replay that copies data into fresh rows under a new
   run (chosen).
3. A separate file-based fixture/cache system outside the database.

**Decision made:** Option 2.

**Reason:** The demo needs to be interactive during replay (editing,
re-validating, approving), and doing that against the original run's
rows would dirty the starting state for future rehearsals. Copying
into a fresh run gives a repeatable clean start using the exact same
downstream pipeline as live mode. A separate fixture-file system
(option 3) would be unnecessary infrastructure — the database already
persists everything needed.

**Trade-offs:** Each replay adds new rows to the database; acceptable
at this single-user, local scale.

**Impact:** Defines the extraction_runs schema fields (`mode`,
`replayed_from_run_id`, `raw_response`) and the demo's reliability
strategy.

**Refinements (added 2026-08-22):**
- `raw_response` is retained for internal debugging/traceability only.
  It is not exposed as a BA-facing UI feature and is not part of the
  normal requirements review workflow.
- A replay must always originate from a `mode='live'` run, and a
  replay run can never itself be replayed — `replayed_from_run_id`
  always points to a live run, never to another replay. The same-row
  part of this rule (the mode/replayed_from_run_id pairing) is
  enforced by a `CHECK` constraint; verifying the referenced row is
  actually `mode='live'` requires application-layer logic, since
  SQLite `CHECK` constraints cannot inspect other rows.

---

## 2026-08-22 — PASS/WARN/FAIL severity framework and rule assignment

**Decision:** Severity is determined by detection confidence ×
workflow significance. FAIL requires both to be high. Only
`DUPLICATE_NEAR` can produce FAIL, and only at its high-confidence
(≥0.90 similarity) threshold. `AMBIGUOUS_WORDING`,
`MISSING_ACCEPTANCE_CONDITION`, `MISSING_ACTOR`, and
`POSSIBLE_CONTRADICTION` are WARN-only.
`POSSIBLE_CONTRADICTION` must always be presented as a possible
contradiction requiring human judgement, never as a confirmed
contradiction.

**Context:** Needed a principled way to assign severity per rule
rather than assigning FAIL based on how serious an issue sounds.

**Options considered:** Severity by issue category/perceived
seriousness vs. severity by confidence × significance (chosen).

**Decision made:** Confidence × significance framework; only
`DUPLICATE_NEAR` reaches FAIL.

**Reason:** Four of the five rules are heuristic and context-blind
with meaningful false-positive rates; approving-with-acknowledgement
(WARN) is the honest representation of what they can actually
guarantee. Only duplicate detection at a high threshold measures
something close to objective (textual overlap), which is why it is
the sole rule allowed to block approval.

**Trade-offs:** A stricter validator could catch more real issues at
FAIL severity, at the cost of blocking approval on heuristics known to
produce false positives. Conservative severity was chosen deliberately
over aggressive detection.

**Impact:** Defines `validation-rules.md` in full and the approval
gating logic.

**Schema note (added 2026-08-22):** `validation_results` stores
`message` (what was found) and `recommended_action` (what the analyst
should consider doing next) as two separate fields, rather than
conflating the explanation and the recommendation into one text
field. Each rule's "Recommended BA action" in `validation-rules.md` is
the source for `recommended_action`.

**Schema clarifications (added 2026-08-22):**
- Every `validation_run` produces exactly one `validation_results` row
  per configured rule, including PASS outcomes — PASS is an explicit
  recorded result, never the absence of a row. This makes "not yet
  validated" and "validated, all clean" distinguishable and keeps the
  validation history fully auditable, per NFR1. A
  `UNIQUE(validation_run_id, rule_id)` constraint enforces no
  duplicate rule results per run at the database level; completeness
  (every configured rule represented) remains application-level
  responsibility.
- `validation_rules.default_severity` is a catalog-level ceiling (the
  most severe outcome a rule can produce), not the actual severity of
  any specific result — that is always `validation_results.result`.
  `DUPLICATE_NEAR`'s `default_severity` is `fail` for this reason. No
  threshold columns are added to `validation_rules`; similarity
  thresholds and severity calculation remain rule logic for a later
  implementation phase.

---

## 2026-08-22 — Two-layer enforcement for FAIL blocking approval

**Decision:** FAIL blocks approval, enforced at both the application
layer (workflow logic, disabled approve action, user messaging) and
the database layer (a `CHECK` constraint on `requirements`:
`review_status != 'approved' OR validation_state != 'fail'`).

**Context:** Needed to decide whether the FAIL-blocks-approval rule
should be enforced only in application code or also at the database
level.

**Options considered:** Application-only enforcement vs. application +
database constraint (chosen).

**Decision made:** Both layers.

**Reason:** The application layer owns the workflow and user-facing
acknowledgement logic; the database constraint is a final integrity
safeguard independent of that logic, and is cheap to implement since
`validation_state` is already denormalised onto the same
`requirements` row.

**Trade-offs:** Minor added schema complexity for a guarantee that
cannot be bypassed by an application-layer bug.

**Impact:** Adds one `CHECK` constraint to the `requirements` table;
does not change the application workflow design.

---

## 2026-08-22 — WARN acknowledgement is persisted, not inferred

**Decision:** Approving a requirement with `validation_state = 'warn'`
requires an explicit acknowledgement action, recorded on the
requirement as `warn_acknowledged_at` / `warn_acknowledged_by`. These
fields are NULL whenever no acknowledgement has occurred, and are
reset to NULL by every new validation run for that requirement.

**Context:** The approval workflow needed a way to prove an analyst
actually saw and considered a WARN result before approving, not just
that the requirement ended up in an approved state.

**Options considered:**
1. Infer acknowledgement from the approval action itself — if a WARN
   requirement is approved, assume the analyst must have seen the
   warning.
2. Persist an explicit acknowledgement record, separate from the
   approval decision (chosen).

**Decision made:** Option 2.

**Reason:** An approval record alone cannot distinguish "the analyst
read this warning and accepted it" from "the analyst clicked approve
without registering that a warning existed." Persisting a dedicated,
timestamped acknowledgement closes that gap and gives the audit trail
real evidentiary value, which is central to this project's
human-in-the-loop story. Resetting the acknowledgement on every new
validation run prevents a stale acknowledgement — made against an
earlier version of the text — from silently covering a different
result later.

**Trade-offs:** Two additional nullable fields and one additional
`CHECK` constraint on `requirements`. This was deliberately kept to a
pair of fields on the existing table rather than a general-purpose
acknowledgement/event log, which would be more infrastructure than
this project's scope justifies.

**Impact:** Adds `warn_acknowledged_at` and `warn_acknowledged_by` to
`requirements`, plus a second `CHECK` constraint alongside the
existing FAIL-blocking constraint. See `architecture.md` and
`validation-rules.md`.

**Refinement (added 2026-08-22):** `warn_acknowledged_by` (and
`requirement_edits.edited_by`, by the same convention) stores the
local OS username of whoever is operating this single-user
application. This is plain audit metadata, not an authentication or
identity system — it must never be described as one. Authentication
and multi-user access remain explicitly out of scope (see
`requirements.md`, `limitations.md`).

---

## 2026-08-22 — MVP scope boundaries

**Decision:** The MVP excludes authentication/multi-user access,
real-time collaboration, delivery-tool integrations (Jira, Azure
DevOps), model fine-tuning, cloud deployment, enterprise security
controls, autonomous AI approval, and a FAIL override workflow.

**Context:** Needed to keep the project focused on demonstrating
requirements-quality workflow and AI/human separation, rather than
becoming a general-purpose delivery tool.

**Options considered:** Broader scope including one or more of the
above vs. a tightly bounded MVP (chosen).

**Decision made:** Tightly bounded MVP as listed.

**Reason:** None of the excluded items contribute to the five-minute
demonstration or the project's core story — AI-assisted extraction,
deterministic validation, and human-controlled approval with
traceability. Adding them would dilute the story without adding to it.

**Trade-offs:** The project cannot demonstrate multi-user review
workflows or exception-based approval, which are realistic in
production BA tooling. This is accepted and documented in
`limitations.md` as a deliberate cut, not an oversight.

**Impact:** Bounds every subsequent design decision; documented in
`requirements.md` and `limitations.md`.

---

## 2026-08-22 — Editing is restricted to pending requirements; no reopening workflow

### The decision

`PATCH /requirements/{id}` only succeeds when `review_status='pending'`.
Editing an already-approved or already-rejected requirement returns
409 Conflict; there is no endpoint or code path that moves a
requirement from `approved`/`rejected` back to `pending`.

### Why

Approval and rejection are meant to be human decisions with real
weight — once an analyst has signed off on a requirement, silently
allowing further edits underneath that decision would let the
approved/rejected state drift away from what the analyst actually
reviewed, without ever being re-reviewed. Blocking edits on decided
requirements keeps "approved" and "rejected" meaning what they say:
a decision was made on a specific, frozen piece of text.

### What I rejected, and why it lost

A reopening workflow (edit an approved/rejected requirement, which
resets it to `pending` for re-review) was considered, since it's a
realistic real-world need. It lost for this milestone because it's a
second lifecycle transition the governing documents never define —
inventing its rules (does it require a reason? does it notify anyone?
can a rejected item be reopened the same way as an approved one?)
would be a new product decision, not an implementation detail, and
this milestone's scope was explicitly the linear pending → decided
path.

### What I'd do differently at production scale

A real system would need a deliberate reopen action — likely its own
endpoint, its own audit trail entry (who reopened it and why), and
probably a policy on whether a previously-approved item needs a fresh
approval or just re-review. That's meaningfully more product design
than "allow editing again," which is exactly why it's deferred rather
than quietly bolted on here.

---

## 2026-08-22 — One composite review endpoint instead of multiple client requests

### The decision

Added `GET /requirements/{id}/review`, which aggregates the
requirement, its originating extracted evidence, its latest validation
results, and its full edit history into a single response, rather than
requiring a future UI to call four separate existing endpoints.

### Why

A human review screen needs all four pieces of information at once —
showing a requirement without its evidence and validation results
isn't a usable review screen. A single endpoint matches how the data
is actually consumed, avoids N+1 round-trips from a future frontend,
and does so purely by composing existing read-only queries — no new
table, no duplicated data, no new domain logic.

### What I rejected, and why it lost

Relying on the three already-existing endpoints
(`GET /requirements/{id}`, `GET /requirements/{id}/validation-results`,
plus a lookup on `extracted-requirements`) was the alternative. It
lost because it pushes composition work onto every future client
instead of once in the API, and because the edit-history piece had no
existing endpoint at all — it would have needed to be added anyway,
just without the other three joined onto it.

### What I'd do differently at production scale

At larger scale, this is where a lightweight query/read-model layer
or GraphQL-style field selection would start to earn its keep, so
screens with different data needs don't each need a bespoke aggregate
endpoint. For a single review screen in a portfolio-scale project,
that would be complexity without a corresponding benefit.

---

## 2026-08-22 — Streamlit for the Module 1 UI, not React/Vite

### The decision

The Module 1 analyst-facing UI is a single-page Streamlit application
(`app/ui/streamlit_app.py`) that calls the existing FastAPI endpoints
over HTTP, rather than the React + Vite frontend originally named in
`architecture.md`'s technology stack.

### Why

Module 1's entire point is the backend workflow — AI drafts,
deterministic rules check, a human decides — and that story is fully
proven by the API and its 176 tests before any UI exists at all.
Streamlit renders that workflow directly in Python from the same
Pydantic response shapes the API already returns, with no separate
build step, no JavaScript, and no new client-side state-management
concern. For a portfolio project whose interview value is the
requirements-quality reasoning, not frontend engineering, that's the
right trade: get a genuinely usable analyst tool in front of the
existing backend with the smallest possible amount of new surface
area.

### What I rejected, and why it lost

React + Vite (the option `architecture.md` originally named) was the
alternative. It lost for this milestone specifically because it would
have meant a real frontend build — routing, a component structure, a
build pipeline, client-side state handling — to display the same data
Streamlit can render directly. That's real engineering effort spent on
something the project's central thesis doesn't depend on. The
architecture doc's original stack table is not being overturned as a
long-term choice, only deferred: if a later milestone genuinely needs
a richer, more polished UI (e.g. the traceability graph view for a
future module), React remains the documented option to revisit then.

### What I'd do differently at production scale

Streamlit is a legitimate choice for an internal analyst tool at
small-to-medium scale, but it doesn't cleanly separate presentation
from a deployable, versioned frontend artifact the way a compiled SPA
does, and its per-interaction full-script rerun model doesn't scale to
a complex, highly interactive multi-user interface. A production
system serving many concurrent analysts would likely need the React
frontend `architecture.md` originally scoped, with the Streamlit app
either retired or kept only as an internal/admin tool.

---

## 2026-08-23 — Module 2 shares validation_runs/validation_results via a nullable dual-FK, not a second validation subsystem

### The decision

`validation_runs` gains a nullable `acceptance_criterion_id` column
alongside the existing (now nullable) `requirement_id` column, with a
`CHECK` constraint enforcing that exactly one of the two is populated
on every row. `validation_results` is unchanged. Two independent
engine functions (`run_validation()` for requirements,
`run_acceptance_criteria_validation()` for acceptance criteria) write
into these same shared tables, each populating only its own FK and
using its own hardcoded rule-code dispatch list.

### Why

Module 2 was explicitly scoped to reuse the existing
`validation_rules`/`validation_runs`/`validation_results` architecture
rather than stand up a parallel validation subsystem for a second
entity type. A nullable dual-FK with an exactly-one-parent `CHECK` is
the standard relational way to let one child table serve two possible
parent types without denormalising the validation-run/result shape
twice. `app/validation_engine.py` needed zero code changes to support
this — it always populates `requirement_id` and never touches
`acceptance_criterion_id`, so requirement validation's behaviour is
provably unaffected by the schema widening.

### What I rejected, and why it lost

A parallel `acceptance_criteria_validation_runs` /
`acceptance_criteria_validation_results` table pair (mirroring
`validation_runs`/`validation_results` exactly but for the new entity)
was the alternative. It lost because it's exactly the "second
validation subsystem" the module was explicitly scoped to avoid — it
would have duplicated the run/result shape, the PASS/WARN/FAIL
vocabulary, and the `UNIQUE(validation_run_id, rule_id)` safeguard for
no structural benefit, at the cost of two more tables and a second
codepath for anything (like a future audit report) that wants "all
validation activity" in one place.

### What I'd do differently at production scale

If a third or fourth entity ever needed deterministic validation, a
literal `(requirement_id, acceptance_criterion_id, ...)` column per
entity type stops scaling cleanly. At that point a single polymorphic
`(parent_type, parent_id)` pair — trading away individual foreign-key
enforcement for a lookup-table or application-level integrity check —
would likely be the better trade, but for exactly two entity types the
explicit dual-FK is more honest and lets the database keep enforcing
referential integrity directly.

---

## 2026-08-23 — Acceptance-criteria live/replay mode is tracked per-record, not per-run

### The decision

`extracted_acceptance_criteria` carries its own `mode`
(`'live'`/`'replay'`) and self-referential `replayed_from_id` columns,
with the same same-row `CHECK` pairing pattern `extraction_runs` uses.
There is no `acceptance_criteria_runs` or equivalent batch/run table.

### Why

Module 1's replay tracking lives on `extraction_runs` because one live
extraction call can produce many candidate requirements sharing one
run. Acceptance-criteria drafting has no batch concept — one live
request drafts exactly one criterion — so there is nothing for a
separate run table to group. Putting `mode`/`replayed_from_id` directly
on `extracted_acceptance_criteria` is the minimal structure that still
lets every criterion answer "was this a live AI call or a replay, and
if a replay, of what" on its own, without inventing a table that would
only ever have a 1:1 relationship with the rows it "batches."

### What I rejected, and why it lost

Adding an `acceptance_criteria_runs` table mirroring `extraction_runs`
exactly was considered, purely for structural symmetry with Module 1.
It lost because a run table whose every row groups exactly one child
row is not doing any grouping — it would be pure overhead copied from
a pattern that solved a problem (one-call-many-candidates) this
module doesn't have.

### What I'd do differently at production scale

If a future capability legitimately let one live request draft several
candidate criteria at once (batch drafting), the run-table pattern
would become the right structure again, and this per-record approach
would need a real migration rather than a graceful extension — that
asymmetry is the main cost of choosing the leaner structure now.

---

## 2026-08-23 — Approval/rejection is a one-way pending transition, and NOT_VALIDATED blocks approval (Module 1 + Module 2)

### The decision

`approve_requirement`/`reject_requirement` and
`approve_acceptance_criterion`/`reject_acceptance_criterion` now only
succeed while the target's `review_status` is `'pending'`; calling
either endpoint again on an already-`approved` or already-`rejected`
row returns 409 Conflict instead of silently changing its status.
Approval is also now blocked outright when `validation_state` is
`'not_validated'`, exactly like the existing FAIL block. Both rules are
enforced at the application layer and, via a new `CHECK` constraint
per table (`ck_requirements_not_validated_blocks_approval`,
`ck_acceptance_criteria_not_validated_blocks_approval`, added in
migration `0003`), at the database layer. A companion recovery
endpoint, `POST /acceptance-criteria/{id}/validate`, was added
mirroring the existing `POST /requirements/{id}/validate`, so a
criterion stranded at `not_validated` (e.g. because validation raised
after its create-transaction already committed) has a way back to a
real PASS/WARN/FAIL outcome without a live AI call.

### Why

This was a defect, not a design gap: `approved`/`rejected` were
intended to be terminal decisions (see the 2026-08-22 entry on
restricting edits to pending requirements), but the approve/reject
routes never actually checked `review_status`, so a rejected item could
be approved seconds later through the same endpoint, and vice versa.
Separately, `not_validated` was never listed in either entity's
FAIL/WARN approval-gating constraints, so a record that had simply
never been validated could be approved as if it had passed. Module 2's
acceptance-criteria routes were built by mirroring Module 1's
requirement routes, so they inherited both gaps byte-for-byte; fixing
both entities together in one change keeps the two workflows
consistent rather than fixing one and leaving the other silently
inconsistent.

### What I rejected, and why it lost

Fixing this at the application layer only (skipping the `CHECK`
constraint change) was considered, since none of the existing
migrations were expected to be needed for this fix. It lost because
the whole point of the existing FAIL-blocking and WARN-acknowledgement
constraints is that the database is the final safeguard independent of
application logic (see the 2026-08-22 entry on two-layer FAIL
enforcement) — leaving `not_validated` as the one ungated case would
have been an inconsistent exception to a principle already established
for this exact table.

A redesign of the two-phase create→validate transaction (folding
validation into the same commit as record creation, so `not_validated`
could never be persisted at all) was also considered as a more thorough
fix for how a criterion ends up stranded at `not_validated` in the
first place. It lost because it would have changed transaction
boundaries that were a deliberate, already-reasoned design choice (see
the acceptance-criteria replay/validation notes), for a case that the
new manual `/validate` recovery endpoint already handles adequately.

### What I'd do differently at production scale

A real system would likely want a structured "reopen" workflow instead
of a flat 409 on any post-decision approve/reject call, so an analyst
who made a mistake has a deliberate, audited way back to `pending`
rather than no way back at all — the same scope boundary already noted
in the 2026-08-22 editing-restriction entry.

---

## 2026-08-23 — Manual re-validation is pending-only; AC_MEASURABLE_THEN's boundary is sentence-based, not word-based; migration 0003 remediates legacy invalid rows

### The decision

Three follow-up fixes to the state-machine fix above, found by an
independent ultra-review of that fix's own commit:

1. `POST /requirements/{id}/validate` and
   `POST /acceptance-criteria/{id}/validate` now return 409 for any
   non-`pending` record, exactly like `PATCH` already does. Previously
   neither endpoint checked `review_status` at all, so re-validating an
   approved WARN record (or one that newly evaluates to FAIL) would
   reset its acknowledgement fields while `review_status` stayed
   `approved`, violating that table's own approval-gating `CHECK`
   constraint and crashing the request with an unhandled 500.
2. `AC_MEASURABLE_THEN`'s Then-clause boundary (added in the previous
   fix pass) now ends at the first sentence-terminal punctuation
   (excluding a decimal point) or a capitalised, sentence-initial
   "Given", whichever comes first — not at any occurrence of the bare
   words "given"/"when". The word-based version fixed the original
   multi-scenario/trailing-prose leakage but introduced a new
   false-negative: a genuinely measurable Then clause using "when" or
   "given" as ordinary English inside its own outcome text (e.g.
   "...locked when 5 attempts occur...", "...shall be given a discount
   of at least 10%...") was wrongly truncated before reaching its own
   measurable evidence.
3. Migration `0003` now resets `review_status` to `pending` for any
   pre-existing row already in the `(review_status='approved',
   validation_state='not_validated')` state — the exact state the
   pre-fix application bug could produce — before adding the `CHECK`
   constraint that forbids it, so the migration cannot fail against a
   database that hit that bug.

### Why

**(1)** Following the exact precedent this project already established
for `PATCH` (see the 2026-08-22 entry on restricting edits to pending
records): once a record's `review_status` leaves `pending`, no
endpoint should be able to mutate the facts approval was granted
against. `/validate` mutates `validation_state` and the WARN
acknowledgement fields, so it needed the same guard `PATCH` already
has. This was chosen over having `/validate` "safely" reopen the
record back to `pending` as a side effect, which would have been a
reopening workflow — something this project has repeatedly and
deliberately declined to build (see the 2026-08-22 and 2026-08-23
entries above). It costs nothing: a criterion or requirement can only
ever be stranded at `not_validated` while still `pending`, since the
prior fix already made it impossible for `not_validated` to become
`approved`.

**(2)** A boundary needs to distinguish a genuine second
Given/When/Then group from an ordinary use of "given"/"when" inside
the first group's own Then clause. Sentence structure is the signal
that actually distinguishes them in every test case this project has:
a second scenario either starts a new sentence, or — in the one
adversarial case without punctuation — is introduced by a capitalised
"Given". An ordinary in-sentence "when"/"given" is neither. Word-only
matching (the previous version) could not tell these apart because it
looked at word identity, not sentence position.

**(3)** The new `CHECK` constraint is only as safe as the data it is
applied to. Since this project's bug window (the P0 state-machine gap)
could have already produced exactly the row shape the constraint now
forbids, adding the constraint without remediating existing data would
make migration `0003` a landmine for any database that lived through
the bug. Resetting to `pending` (rather than deleting the row or
leaving it broken) was chosen because it is the state the corrected
application logic would have left the record in, and it forces a
fresh, informed approval decision rather than silently granting one.

### What I rejected, and why it lost

For (1): weakening or removing the `CHECK` constraints instead of
guarding the endpoint was not seriously considered — the explicit
instruction for this fix pass was to strengthen constraints, not
relax them, and the constraint is doing exactly its job by catching
the bug.

For (2): dropping the boundary fix entirely (reverting to scanning to
end-of-string) was rejected because it would resurrect the original
multi-scenario/trailing-prose false-positive this project's previous
fix pass was specifically about closing. A pure "sentence-only"
boundary (dropping the capitalised-"Given" fallback) was also
considered and rejected because it fails the adversarial case where a
second scenario is comma-joined without a sentence break — the
combined heuristic handles both known failure modes with no new
regressions found in either direction.

For (3): leaving migration 0003 as originally shipped and simply
documenting the failure mode as "intentionally unsupported" was
considered, given this project's single-user, no-real-deployment
scope. It lost because the remediation costs two `UPDATE` statements
and has no downside — it is not the kind of production-migration
tooling (backfill jobs, blue/green cutover, etc.) that was scoped out
as P3; it is the minimum a correct migration owes to the exact bug the
constraint it's adding was written to catch.

### What I'd do differently at production scale

For (2): the residual gap — a second scenario using a lowercase
"given" with no sentence break before it — would need either a
stricter authoring convention (always capitalise scenario-starting
keywords) enforced upstream, or a real grammatical parse instead of
regex heuristics, to close completely. Neither is justified for this
project's scope; see `validation-rules.md`'s "Known limitations" for
`AC_MEASURABLE_THEN`.
