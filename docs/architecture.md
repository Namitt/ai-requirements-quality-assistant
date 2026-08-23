# Architecture

## Technology stack

| Layer | Choice | Notes |
|---|---|---|
| Backend | Python + FastAPI | REST API serving the frontend |
| Database | SQLite | Single-file, relational, sufficient for single-user local scope |
| Data access | SQLAlchemy | Explicit models, explicit foreign keys |
| AI provider | Anthropic API | Used only for extraction, never for validation |
| Frontend | React + Vite | Deliberately small — this is a BA/DA project, not a frontend showcase |
| Testing | pytest | Validator tested against a fixed reference fixture |

See `decisions-log.md` for the reasoning behind each of these choices
and the alternatives considered.

## Why relational, not graph

Every relationship in this system is a simple one-to-many chain:
source document → extraction run → extracted requirement → requirement
→ validation run → validation result, plus an edit history off the
requirement. There is no variable-depth traversal, no arbitrary
relationship typing, and no query pattern that benefits from a graph
model. Foreign keys and joins express the full data model without
added conceptual or operational overhead.

## Why deterministic validation, not LLM-based validation

The validator's entire credibility rests on being explainable: every
result must be traceable to a specific, inspectable rule. An LLM asked
"is this requirement good?" produces a plausible-sounding judgement
that cannot be audited the same way, and would blur the project's core
distinction between AI-generated content and validated content. All
five validation rules are pattern/structure checks over text, not
model calls.

## System components

- **Ingestion** — accepts raw source text, stores it as a source
  document.
- **Extraction** — either calls the Anthropic API (live mode) or
  replays a previously captured result (replay mode); produces
  immutable AI-output records paired with reviewable requirements.
- **Validation engine** — runs the five deterministic rules against
  requirement text and produces PASS/WARN/FAIL results, each with an
  explanation and a recommended action; runs automatically after
  extraction and again after every edit.
- **Review & approval** — supports human editing, an explicit WARN
  acknowledgement action (recorded on the requirement, not inferred
  from the approval itself), and approve/reject decisions.
- **Traceability** — links every requirement back to its AI origin and
  the exact source text span.
- **Summary/audit view** — reports AI origin, validation outcome, and
  human decision per requirement, and in aggregate.

## Data model

```
source_documents(
  id, title, raw_text, created_at
)

extraction_runs(
  id, source_document_id FK,
  model_name, prompt_version,
  mode CHECK (mode IN ('live','replay')),
  replayed_from_run_id FK NULL -> extraction_runs.id,
  raw_response NULL,
  run_at,
  CHECK (
    (mode = 'live' AND replayed_from_run_id IS NULL)
    OR (mode = 'replay' AND replayed_from_run_id IS NOT NULL)
  )
)
-- raw_response is retained for internal debugging/traceability only.
-- It is never exposed as a BA-facing UI feature and is not part of
-- the normal requirements review workflow.
-- A replay run's replayed_from_run_id must reference a run with
-- mode='live' — a replay can never itself be replayed. SQLite cannot
-- express that cross-row condition in a CHECK constraint (a CHECK can
-- only see the current row), so that specific part of the rule is
-- enforced at the application layer; the CHECK above only enforces
-- the same-row pairing of mode and replayed_from_run_id.
-- model_name and prompt_version are always populated, on both live
-- and replay rows. On a replay row they are copied from the original
-- live run as denormalised traceability metadata, so the row is
-- self-contained and inspectable on its own. Copying them does NOT
-- mean the model was called again — replayed_from_run_id remains the
-- authoritative link to the original live call.

extracted_requirements(
  id, extraction_run_id FK,
  requirement_text,
  source_span_start, source_span_end, source_quote,
  created_at
)
-- Immutable. Never edited after creation, regardless of what happens
-- to the paired requirement (edited, rejected, merged, replaced).

requirements(
  id, source_extraction_id FK NULL -> extracted_requirements.id,
  current_text,
  origin CHECK (origin IN ('ai_generated','manual')),
  validation_state DEFAULT 'not_validated'
    CHECK (validation_state IN ('not_validated','pass','warn','fail')),
  review_status DEFAULT 'pending'
    CHECK (review_status IN ('pending','approved','rejected')),
  warn_acknowledged_at NULL,
  warn_acknowledged_by NULL,
  created_at, updated_at,
  CHECK (review_status != 'approved' OR validation_state != 'fail'),
  CHECK (
    review_status != 'approved'
    OR validation_state != 'warn'
    OR warn_acknowledged_at IS NOT NULL
  )
)
-- The mutable, reviewable, approvable entity. One is created
-- automatically for every extracted_requirements row at extraction
-- time. source_extraction_id is nullable to allow manually authored
-- requirements (e.g. splitting one AI candidate into two).
-- warn_acknowledged_at / warn_acknowledged_by are NULL whenever no
-- WARN acknowledgement has occurred, and are set only when the
-- analyst explicitly acknowledges a WARN result immediately before
-- approving it. They are never inferred from review_status alone.
-- Every new validation_run for a requirement resets both fields to
-- NULL, so an acknowledgement can never carry forward to a validation
-- result the analyst has not actually seen.

requirement_edits(
  id, requirement_id FK,
  previous_text, new_text,
  edited_by, edited_at
)
-- Edit history is the single source of truth for "was this edited" —
-- no redundant boolean is stored on requirements.

validation_rules(
  id, code, name, description, default_severity
)
-- default_severity is a catalog-level ceiling: the most severe
-- outcome the rule is capable of producing, not the actual severity
-- of any specific result. DUPLICATE_NEAR's default_severity is
-- 'fail' because it can reach FAIL at its high-confidence tier; an
-- individual validation_results.result for that rule may still be
-- 'warn' or 'pass'. No threshold or configuration columns are added
-- here — similarity thresholds and severity calculation are rule
-- logic, implemented in a later phase, not schema.

validation_runs(
  id, requirement_id FK, validator_version, run_at
)
-- Every edit to a requirement's text triggers a new validation_run
-- before that requirement can be approved. A previous validation
-- result is never left in place as though still authoritative once
-- the text has changed. requirements.validation_state is always a
-- cached copy of the latest validation_run's worst result — it is
-- never edited directly.

validation_results(
  id, validation_run_id FK, rule_id FK,
  result CHECK (result IN ('pass','warn','fail')),
  message, recommended_action, created_at,
  UNIQUE (validation_run_id, rule_id)
)
-- message explains what the rule found; recommended_action states
-- what the analyst should consider doing next. Kept as two plain
-- text fields rather than a structured sub-model.
-- Every validation_run produces exactly one validation_results row
-- per configured rule (five rows for the current rule set), including
-- PASS outcomes. PASS is always an explicit recorded result, never
-- the absence of a row — this is what lets "not yet validated" and
-- "validated, all clean" be told apart.
-- UNIQUE(validation_run_id, rule_id) is a database-level safeguard
-- against the same rule being recorded twice for one run. It does not
-- by itself guarantee completeness — ensuring every configured rule
-- produces exactly one result per run remains application logic,
-- implemented in a later phase.
```

### Requirement lifecycle fields

`requirements` uses three independent fields rather than one combined
status, because origin, validation outcome, and human decision are
independent facts:

- **origin** — `ai_generated` or `manual`. Set once at creation.
- **validation_state** — cached copy of the latest validation run's
  worst result (`not_validated`, `pass`, `warn`, `fail`). Source of
  truth is always `validation_results`; this column is recomputed
  after every validation run, never edited directly.
- **review_status** — `pending`, `approved`, or `rejected`. The
  human-controlled workflow gate.
- **warn_acknowledged_at / warn_acknowledged_by** — NULL unless the
  analyst has explicitly acknowledged a WARN result immediately before
  approving. Approval is never treated as implicit evidence that a
  WARN was seen — the acknowledgement must be recorded separately. Any
  new validation_run resets both fields to NULL. `warn_acknowledged_by`
  stores the local OS username of whoever is operating this
  single-user application — plain audit metadata identifying which
  local user acted, not an authentication or identity system. The
  application still has no login, no user accounts, and no access
  control (see `limitations.md`).

Whether a requirement has been edited is derived from the presence of
rows in `requirement_edits`, not stored as a separate field.
`requirement_edits.edited_by` uses the same OS-username convention as
`warn_acknowledged_by` above, for the same reason.

### Approval enforcement (two layers)

The approval rule is: PASS requires no acknowledgement; WARN requires
explicit acknowledgement; FAIL blocks approval outright. Both parts of
this rule are enforced twice:

1. **Application layer** — owns the workflow: disables the approve
   action and explains why when `validation_state = 'fail'`; requires
   the analyst to explicitly acknowledge a `warn` result (setting
   `warn_acknowledged_at` / `warn_acknowledged_by`) before the approve
   action becomes available.
2. **Database layer** — two `CHECK` constraints on `requirements` act
   as a final integrity safeguard, independent of the application
   logic above them:
   - `review_status != 'approved' OR validation_state != 'fail'`
   - `review_status != 'approved' OR validation_state != 'warn' OR warn_acknowledged_at IS NOT NULL`

   Together these mean the database itself cannot contain an approved
   requirement that is either FAIL, or WARN without a recorded
   acknowledgement.

### Deletion behaviour

All foreign keys use RESTRICT (no cascading deletes). Nothing in the
documented workflow deletes source documents, extraction runs,
requirements, or validation history, and audit-linked records are
deliberately protected from being silently removed as a side effect of
deleting a parent row. There is no user-facing deletion feature.

## Live vs. replay mode

**Live:**
`source_documents` → Anthropic API call → new `extraction_runs` row
(`mode='live'`, `raw_response` stored) → `extracted_requirements` rows
→ paired `requirements` rows → validation.

**Replay:**
An existing `extraction_runs` row (`mode='live'`) is selected → a new
`extraction_runs` row is created (`mode='replay'`,
`replayed_from_run_id` pointing at the original) → the original run's
`model_name`/`prompt_version` are copied onto the new row as
denormalised traceability metadata, and its `extracted_requirements`
text/spans are copied into fresh rows under the new run → fresh paired `requirements` rows are created → the same
validation/review/approval pipeline runs, identically to live mode. No
API call is made. The UI always shows replayed content as "replayed
from a saved run," never as a new model result.

A replay must always originate from a `mode='live'` run, and a replay
run can never itself be replayed — `replayed_from_run_id` always
points to a live run, never to another replay. This keeps every
replay chain exactly one hop from a real AI call, so "what did the AI
actually produce" is never ambiguous.

No separate cache or fixture-file system is used — the database is the
only store, for both live and replayed data.

## AI role and boundaries

AI is used for exactly one function: extracting candidate requirements
from source text. It never validates, never approves, and the system
never presents AI output as though it has already been judged correct.
`origin='ai_generated'` content is visually and structurally
distinguishable from human-edited or manually authored content
throughout the review and summary views.

---

# Module 2 — Acceptance Criteria Assistant

## System components (additive)

- **Acceptance-criteria drafting** — either calls the Anthropic API
  (live mode, reusing the same `ExtractionClient` abstraction Module 1
  uses) or replays a previously captured live draft (replay mode);
  produces one immutable AI-output record paired with one reviewable
  acceptance criterion.
- **Acceptance-criteria validation engine** — runs four deterministic
  structural rules against a criterion's text and produces PASS/WARN
  results (no v1 rule can produce FAIL), each with an explanation and a
  recommended action; runs automatically after drafting and again after
  every edit. Reuses the existing `validation_rules` /
  `validation_runs` / `validation_results` tables rather than a second
  validation subsystem.
- **Review & approval** — the same edit / WARN-acknowledgement /
  approve / reject shape as Module 1, applied to acceptance criteria
  independently of their parent requirement.
- **Traceability** — links every criterion back to the requirement it
  was drafted for, and through that requirement to its own extracted
  evidence and source document.

## Data model (additive)

```
extracted_acceptance_criteria(
  id, requirement_id FK -> requirements.id,
  criterion_text,
  mode CHECK (mode IN ('live','replay')),
  replayed_from_id FK NULL -> extracted_acceptance_criteria.id,
  model_name, prompt_version,
  created_at,
  CHECK (
    (mode = 'live' AND replayed_from_id IS NULL)
    OR (mode = 'replay' AND replayed_from_id IS NOT NULL)
  )
)
-- Immutable. No raw_response column - unlike extraction_runs, there is
-- no run/batch concept for acceptance criteria (each live request
-- drafts exactly one criterion), so live/replay tracking lives
-- directly on this record rather than on a separate run table, and a
-- replay's replayed_from_id must reference a row with mode='live' -
-- enforced at the application layer, mirroring extraction_runs'
-- equivalent replay-source rule.

acceptance_criteria(
  id, source_extraction_id FK NOT NULL -> extracted_acceptance_criteria.id,
  current_text,
  validation_state DEFAULT 'not_validated'
    CHECK (validation_state IN ('not_validated','pass','warn','fail')),
  review_status DEFAULT 'pending'
    CHECK (review_status IN ('pending','approved','rejected')),
  warn_acknowledged_at NULL, warn_acknowledged_by NULL,
  created_at, updated_at,
  CHECK (review_status != 'approved' OR validation_state != 'fail'),
  CHECK (
    review_status != 'approved'
    OR validation_state != 'warn'
    OR warn_acknowledged_at IS NOT NULL
  )
)
-- The mutable, reviewable, approvable entity - identical lifecycle
-- shape to requirements, minus an origin field: every acceptance
-- criterion is AI-origin in this version, so source_extraction_id is
-- NOT NULL (unlike requirements.source_extraction_id, which is
-- nullable to support manually authored requirements).

acceptance_criteria_edits(
  id, acceptance_criterion_id FK -> acceptance_criteria.id,
  previous_text, new_text, edited_by, edited_at
)
-- Append-only, identical shape and purpose to requirement_edits.
```

`validation_runs` is extended, not duplicated, to serve both modules:

```
validation_runs(
  id,
  requirement_id FK NULL -> requirements.id,
  acceptance_criterion_id FK NULL -> acceptance_criteria.id,
  validator_version, run_at,
  CHECK (
    (requirement_id IS NOT NULL AND acceptance_criterion_id IS NULL)
    OR (requirement_id IS NULL AND acceptance_criterion_id IS NOT NULL)
  )
)
```

`requirement_id` was `NOT NULL` in Module 1; it is widened to nullable
here so the same table can represent either kind of validation run,
with the `CHECK` constraint guaranteeing every row has exactly one
parent. `app/validation_engine.py` is unmodified and always populates
`requirement_id`, so this change has no effect on requirement
validation's behaviour. `validation_results` is unmodified — it is
agnostic to which kind of parent its `validation_run` belongs to.

## Rule dispatch stays separate

`app/validation_engine.py::EXPECTED_RULE_CODES` (5 requirement codes)
and `app/acceptance_criteria_validation_engine.py::EXPECTED_AC_RULE_CODES`
(4 acceptance-criteria codes) are two independent, hardcoded dispatch
lists in two independent engine functions. `validation_rules` holds all
nine rows as one descriptive catalog, but the catalog itself never
determines which rules execute for which entity — exactly the same
non-plugin design Module 1 already established, just with two dispatch
lists instead of one.

## Live vs. replay mode (acceptance criteria)

**Live:** a requirement's `current_text` → Anthropic API call (same
`ExtractionClient` as Module 1) → new `extracted_acceptance_criteria`
row (`mode='live'`) → paired `acceptance_criteria` row → validation.

**Replay:** an existing `extracted_acceptance_criteria` row
(`mode='live'`) is selected → a new row is created (`mode='replay'`,
`replayed_from_id` pointing at the original, `requirement_id`,
`criterion_text`, `model_name`, `prompt_version` all copied) → a fresh
paired `acceptance_criteria` row is created → the same
validation/review/approval pipeline runs. No API call is made. A
replay can never itself be replayed, mirroring Module 1's replay-chain
rule exactly.

## AI role and boundaries (acceptance criteria)

AI is used for exactly one function here too: drafting one Given/When/
Then acceptance criterion from a requirement's text. It never
validates, never approves, and a PASS structural result is never
presented as a claim that the criterion is business-correct or
QA-ready.
