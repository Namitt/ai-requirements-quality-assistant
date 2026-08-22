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
