# Validation Rules

## Purpose and scope

This document defines the deterministic rules used to check extracted
and reviewed requirements. The validator identifies defined textual
and structural patterns. It does not determine whether a requirement
is correct from a business perspective — that judgement remains with
the analyst.

## Result semantics

- **PASS** — No issue was detected by the configured checks that ran.
  This is not a claim that the requirement is correct.
- **WARN** — A potential issue was detected. It requires analyst
  judgement and does not block approval, but approval requires
  explicit acknowledgement.
- **FAIL** — A high-confidence deterministic condition was not
  satisfied and requires correction before approval. Blocks approval.

Each validation result stores two distinct pieces of text: `message`
(what was found — the explanation) and `recommended_action` (what the
analyst should consider doing next). In the per-rule definitions
below, the "Recommended BA action" line is the source for
`recommended_action`; the rest of each rule's description is the
source for `message`.

## Severity framework

Severity is set from two independent factors:

1. **Detection confidence** — how sure the rule can be that it
   detected the condition it claims to detect, rather than a
   coincidence or a context it cannot see.
2. **Workflow significance** — if the condition is real, how much it
   matters for whether the requirement is ready to move into
   delivery.

FAIL requires both factors to be high. A rule is never set to FAIL
because the underlying issue sounds serious on its own — only when
detection is close to objective measurement and the condition would
genuinely need correcting before sign-off.

Under this framework, only `DUPLICATE_NEAR` can produce FAIL, and only
at its high-confidence threshold (≥0.90 similarity). The other four
rules are WARN-only, because their detection is heuristic and
context-blind, or because the condition they detect is often a
legitimate judgement call rather than a defect.

## Comparison scope

`DUPLICATE_NEAR` and `POSSIBLE_CONTRADICTION` compare a requirement's
current text against every other non-rejected requirement that
resolves, via `source_extraction_id → extracted_requirements →
extraction_run_id → extraction_runs → source_document_id`, to the
same `source_documents` row. This is document-wide: it spans every
extraction run — live or replay — ever run against that document, not
just the batch the requirement was originally extracted in.

Requirements with `origin='manual'` have a NULL `source_extraction_id`
and therefore have no resolvable source document under the current
schema. They are excluded from document-scoped `DUPLICATE_NEAR` and
`POSSIBLE_CONTRADICTION` comparison in this version — never compared
against other requirements, and never compared against, by these two
rules. This is a known, schema-driven limitation, not an oversight
(see `limitations.md`).

Replay-generated requirements are compared using their own extraction
run's `source_document_id`, trusted by the same convention already
applied to `replayed_from_run_id` — the database does not separately
re-verify that a replay's source document matches its originating
live run.

## Multi-sibling aggregation

`DUPLICATE_NEAR` and `POSSIBLE_CONTRADICTION` are defined in terms of
a single pairwise comparison, but each produces exactly one
`validation_results` row per validation run. When a requirement has
more than one eligible sibling in its comparison scope, the rule
evaluates every eligible pair and selects the single worst outcome,
using severity ordering FAIL > WARN > PASS. For `DUPLICATE_NEAR`, one
sibling at ≥ 0.90 similarity determines FAIL even if every other
sibling only reaches WARN or PASS. For `POSSIBLE_CONTRADICTION` —
WARN-only under all circumstances — the presence of any single
qualifying pair produces WARN.

If two or more candidate siblings tie on severity, the tie is broken
first by the higher similarity score, then, if still tied, by the
lower requirement ID — a deterministic, reproducible choice.

The resulting `message` identifies the specific sibling requirement
that produced the selected result (e.g. by its ID). Matching siblings
are not concatenated into one combined message.

## Rules

### DUPLICATE_NEAR — Duplicate / near-duplicate

- **Purpose:** Catch requirements that restate an existing one,
  creating redundant or conflicting requirements downstream.
- **Checked:** Similarity of a requirement's current text against
  every other non-rejected requirement's current text within the same
  source document.
- **Detection approach:** Normalize text (lowercase, strip
  punctuation, collapse whitespace, trim surrounding whitespace),
  then score similarity with Python's standard-library
  `difflib.SequenceMatcher.ratio()` on the two normalized strings.
  Thresholds: < 0.70 = PASS; ≥ 0.70 and < 0.90 = WARN; ≥ 0.90 = FAIL.
  If either side is empty or whitespace-only after normalization, the
  pair is never treated as a match, regardless of the score
  `SequenceMatcher` would otherwise report (1.0, for two empty
  strings) — no numeric minimum-length threshold is used. Evaluated
  against every eligible sibling in the requirement's comparison
  scope (see "Comparison scope" above); the worst pairwise outcome is
  selected per "Multi-sibling aggregation" above.
- **Confidence:** High at ≥0.90 — this measures textual overlap
  directly, not inferred meaning. Medium at 0.70–0.89.
- **False-positive risk:** Low at the high tier; moderate at the mid
  tier, where related-but-distinct requirements can share vocabulary.
- **False-negative risk:** High for semantic duplicates phrased
  differently — a deliberate limitation of staying deterministic.
- **Severity:** FAIL at ≥0.90, WARN at 0.70–0.89.
- **Blocks approval:** FAIL tier only.
  Examples below are illustrative, showing the similarity score each
  pair actually measures under `difflib.SequenceMatcher.ratio()` on
  normalized text, per the resulting tier.
- **PASS example:** "The system shall export reports as CSV." vs.
  "The system shall lock accounts after 5 failed logins." (similarity
  ≈ 0.56.)
- **FAIL example:** "The system shall send a confirmation email after
  the user registers." vs. "The system shall send a confirmation
  email after a user registers." (similarity ≈ 0.97 — a near-exact
  restatement of the same requirement.)
- **WARN example:** "The system shall log all failed login attempts."
  vs. "The system shall record failed login attempts for security
  review." (similarity ≈ 0.72 — the same underlying requirement,
  worded differently enough to need a human decision.)
- **Recommended BA action:** FAIL — decide which is canonical, reject
  or merge the other. WARN — confirm whether the two are duplicates or
  legitimately distinct.
- **Known limitations:** Text-similarity only, not semantic; will not
  catch duplicates phrased very differently. The only rule permitted
  to FAIL, and only at a narrow, high-confidence band.

### AMBIGUOUS_WORDING — Ambiguous wording

- **Purpose:** Flag subjective or untestable terms.
- **Checked:** Presence of terms from a fixed, documented list (e.g.
  "user-friendly", "fast", "appropriate", "as needed", "TBD",
  "reasonable", "intuitive", "robust", "flexible", "easy to use",
  "adequate").
- **Detection approach:** Case-insensitive, word-boundary match
  against the list; reports the exact term found and its position.
- **Confidence:** High that the term is present; low that its
  presence alone proves the sentence is unacceptably vague, since the
  check cannot see surrounding context.
- **False-positive risk:** Moderate–high — a listed term can appear in
  an otherwise precise sentence.
- **False-negative risk:** High — vague phrasing outside the curated
  list is not caught.
- **Severity:** WARN only.
- **Blocks approval:** No.
- **PASS example:** "The system shall lock a user account after 5
  consecutive failed login attempts within 10 minutes."
- **WARN example:** "The system shall provide a user-friendly
  interface for account management."
- **Recommended BA action:** Rewrite with a measurable criterion if
  genuinely vague; otherwise dismiss with acknowledgement.
- **Known limitations:** Fixed vocabulary, no contextual
  understanding, English-only. The term list is maintained as
  configuration, not hardcoded logic, so it can be extended.

### MISSING_ACCEPTANCE_CONDITION — Missing acceptance condition

- **Purpose:** Flag requirements lacking a measurable or testable
  condition.
- **Checked:** Presence of a number-plus-unit pattern, a
  comparison/threshold phrase ("at least", "no more than", "within"),
  or a conditional connector ("if", "when", "unless", "until").
- **Detection approach:** Regex patterns for the three signal types;
  flagged if none are found anywhere in the requirement text.
- **Confidence:** Medium — absence of a match is a real signal, but
  many valid requirements are legitimately non-quantitative.
- **False-positive risk:** High — the highest of the five rules.
  Functional/capability requirements are often testable without
  matching these specific patterns.
- **False-negative risk:** Moderate — a number can be present without
  being an acceptance condition.
- **Severity:** WARN only.
- **Blocks approval:** No.
- **PASS example:** "The page shall load within 2 seconds for 95% of
  requests under normal load."
- **WARN example:** "The system shall provide reporting capabilities
  for administrators."
- **Recommended BA action:** Add a measurable condition if the
  requirement is meant to be delivery-ready, or approve as-is if it is
  intentionally a high-level statement awaiting decomposition.
- **Known limitations:** Highest false-positive rate in the rule set —
  presented to the analyst as the weakest-confidence check.

### MISSING_ACTOR — Missing actor

- **Purpose:** Flag requirements with no clear subject performing the
  action.
- **Checked:** Whether the sentence identifies an actor (a configured
  list: "the system", "the user", named roles, "administrators", etc.)
  before or within the main clause.
- **Detection approach:** Pattern match against the known-actor list;
  flags passive constructions with no actor and no "by X" clause.
- **Confidence:** Medium-high for clear passive constructions; lower
  for compound or complex sentences.
- **False-positive risk:** Moderate — non-standard but valid phrasing
  can be missed by the pattern set.
- **False-negative risk:** Moderate — a grammatical subject can exist
  without being a real responsible actor.
- **Severity:** WARN only.
- **Blocks approval:** No.
- **PASS example:** "The system shall validate the uploaded file
  format before accepting it."
- **WARN example:** "The uploaded file shall be validated before
  acceptance."
- **Recommended BA action:** Rewrite to name the responsible actor if
  clarity matters for delivery; approve if the actor is obvious from
  surrounding context.
- **Known limitations:** Actor list is necessarily incomplete; this is
  not a full grammatical parse.

### POSSIBLE_CONTRADICTION — Possible contradiction

- **Purpose:** Surface requirement pairs that appear to set
  conflicting rules for the same subject. The highest-stakes issue in
  the set, and the least reliable to detect — must never be described
  as "contradiction detected," only as a possible contradiction
  requiring human judgement.
- **Checked:** Pairs of requirements, within the comparison scope
  defined above, that (a) reach the same ≥ 0.70 similarity threshold
  used as `DUPLICATE_NEAR`'s WARN floor — no separate contradiction
  threshold is used — and (b) either state different numeric values
  for a number-plus-unit occurrence extracted using the same pattern
  as `MISSING_ACCEPTANCE_CONDITION`, or one contains a negation
  ("not"/"shall not") that the other lacks on an otherwise
  near-identical sentence.
- **Detection approach:** Deliberately narrow — both conditions must
  hold before a pair is flagged. The numeric case only establishes
  that two extracted numbers differ on an already-similar pair; it
  does not verify the two numbers describe the same business
  attribute beyond that similarity. No semantic or NLP-level subject
  extraction is attempted, and no external NLP library or LLM is
  used — this is an intentionally heuristic, deterministic
  approximation, consistent with this being the weakest rule in the
  set. Aggregated across siblings per "Multi-sibling aggregation"
  above.
- **Confidence:** Low-to-medium — the weakest rule in the set; it can
  only catch contradictions that manifest as a textual or numeric
  mismatch on similar sentences.
- **False-positive risk:** High — shared vocabulary with different,
  non-conflicting scope (different actor, different feature) can
  appear to be a contradiction.
- **False-negative risk:** Very high — most real contradictions share
  little vocabulary or require business knowledge to recognise.
- **Severity:** WARN only, always.
- **Blocks approval:** No.
- **PASS example:** Two requirements on unrelated subjects, or the
  same subject with consistent values.
- **WARN example:** "The system shall lock a user account after 5
  failed login attempts." vs. "The system shall lock a user account
  after 3 failed login attempts."
- **Recommended BA action:** Manually compare the two flagged
  requirements (always shown together); determine genuine
  contradiction vs. legitimately different scope; correct or annotate.
- **Known limitations:** High false positives, very high false
  negatives. A semantic/LLM-based contradiction detector was
  considered and rejected in favour of staying deterministic and
  explainable, at the cost of recall. Always presented to the analyst
  as "possible contradiction — requires human judgement."

## Approval gating

- **PASS** — no acknowledgement required; approval can proceed
  directly.
- **WARN** — approval requires an explicit acknowledgement action,
  which is recorded on the requirement (`warn_acknowledged_at`,
  `warn_acknowledged_by`) rather than inferred from the approval
  itself. This is deliberate: an approval record alone cannot prove
  the analyst actually saw and considered the warning.
- **FAIL** — blocks approval outright. There is no FAIL override
  workflow in the MVP (see `limitations.md`).
- **NOT_VALIDATED** — blocks approval outright. A requirement that has
  never been validated (or whose validation is still pending after an
  edit) cannot be approved; deterministic validation must run and
  produce a real PASS/WARN/FAIL outcome first.

Both the FAIL block, the NOT_VALIDATED block, and the WARN
acknowledgement requirement are enforced at the application layer
(workflow and user messaging) and the database layer (`CHECK`
constraints as a final safeguard — see `architecture.md`).

`pending`, `approved`, and `rejected` are one-way terminal states once
an analyst decides: approving or rejecting a requirement is only
permitted while it is `pending`. An already-approved or already-rejected
requirement cannot be silently re-approved or re-rejected by calling
the same endpoint again — the API returns a 409 conflict instead.

`POST /requirements/{id}/validate` is subject to the same `pending`-only
rule: it also returns 409 for an already-approved or already-rejected
requirement, for the same reason `PATCH` does. Re-running validation
recomputes `validation_state` and resets the WARN acknowledgement
fields, which is exactly the kind of underlying-fact mutation the
`pending`-only rule exists to prevent once a decision has been made —
without this guard, re-validating an approved WARN requirement (or one
that newly evaluates to FAIL) would try to write a
`review_status='approved'` row that violates its own approval-gating
`CHECK` constraint. Rejecting the call up front, before any mutation is
attempted, is how that is avoided; the endpoint does not attempt to
"safely" reset the requirement back to `pending` as a side effect,
since that would be a reopening workflow this project has deliberately
not built.

Editing or revalidating a requirement invalidates any existing WARN
acknowledgement: every new validation run resets
`warn_acknowledged_at` and `warn_acknowledged_by` to NULL, so a stale
acknowledgement can never carry forward to a validation result the
analyst has not actually seen. A fresh acknowledgement is required
before a requirement can be approved again.

## Engine execution model

- **Rule dispatch:** the validation engine runs exactly five
  hardcoded rule functions, in the fixed order `DUPLICATE_NEAR`,
  `AMBIGUOUS_WORDING`, `MISSING_ACCEPTANCE_CONDITION`,
  `MISSING_ACTOR`, `POSSIBLE_CONTRADICTION`. `validation_rules` is a
  seeded, descriptive catalog only — it is not a plugin system and
  does not determine which code executes. If the catalog is missing
  any of the five expected codes, that is treated as a configuration
  error and the run fails rather than silently executing fewer rules.
- **Atomicity:** a validation run is all-or-nothing. If any rule
  raises an unexpected exception, no `validation_runs` row, no
  `validation_results` rows, no `requirements.validation_state`
  update, and no acknowledgement reset are persisted — the
  transaction rolls back and the exception propagates to the caller.
  This follows directly from the approved schema: there is no
  `'error'` result value, and every successful run must produce
  exactly five results, so a partial run cannot be represented.
- **`validator_version`:** a hardcoded implementation constant
  (`"1.0.0"`), incremented by hand when validation logic materially
  changes. Not derived from packaging, source hashing, or version
  control.
- **History:** every successful validation run is additive — a new
  `validation_runs` row and five new `validation_results` rows.
  Previous runs are never overwritten. `requirements.validation_state`
  remains only a cached pointer to the latest run's worst result.

## Module 2 — Acceptance-criteria structural rules

### Purpose and scope

Four additional deterministic rules check AI-drafted Given/When/Then
acceptance criteria (Module 2). They share the same `validation_rules`
/ `validation_runs` / `validation_results` tables and the same
PASS/WARN/FAIL vocabulary as the five requirement rules above, but are
dispatched by a separate, independent engine
(`app/acceptance_criteria_validation_engine.py`) against
`acceptance_criteria` rows, never against `requirements` rows. Like the
requirement rules, none of these determine whether a criterion is
correct from a business or QA perspective — that judgement remains
with the analyst.

### Severity for this rule set

All four rules are **WARN-only** in this version — none can produce
FAIL. Applying the same confidence × significance framework used for
the five requirement rules: each rule can only confirm the *literal
absence of a keyword or pattern*, not that the underlying Given/When/
Then structure is genuinely missing (an analyst could phrase a valid
clause without the expected word), so none reaches the "detection
confidence" bar FAIL requires — the same reasoning that keeps
`MISSING_ACTOR` and the other three requirement rules WARN-only. The
FAIL-blocking application and database enforcement is still fully
implemented for this entity (see "Approval gating" below), so it is
ready if a future, stricter rule is ever added — it is simply
unreachable through the current four rules.

### Comparison scope

None of the four rules compares a criterion against any other
criterion or requirement. Each evaluates a single criterion's own text
in isolation.

### AC_GIVEN_PRESENT — Given clause present

- **Purpose:** Flag acceptance criteria missing a Given clause.
- **Checked:** Case-insensitive, word-boundary match for the literal
  word "given" anywhere in the criterion text.
- **Confidence:** High that the word is present or absent; low that
  its absence alone proves the criterion lacks a starting-context
  clause, since a valid clause could be phrased without that word.
- **Severity:** WARN only.
- **Blocks approval:** No.
- **PASS example:** "Given a user with 5 failed login attempts, when
  they retry, then the system shall lock the account within 2
  seconds."
- **WARN example:** "When the user retries, then the system shall lock
  the account within 2 seconds."
- **Recommended BA action:** Add a Given clause describing the
  starting context, or confirm the criterion is intentionally
  structured differently.
- **Known limitations:** Keyword presence only, not a grammatical
  parse.

### AC_WHEN_PRESENT — When clause present

- **Purpose:** Flag acceptance criteria missing a When clause.
- **Checked:** Case-insensitive, word-boundary match for "when".
- **Confidence / false-positive / false-negative risk:** Same
  reasoning as AC_GIVEN_PRESENT, applied to "when".
- **Severity:** WARN only. **Blocks approval:** No.
- **PASS example:** As AC_GIVEN_PRESENT's PASS example.
- **WARN example:** "Given a user with 5 failed login attempts, then
  the system shall lock the account within 2 seconds."
- **Recommended BA action:** Add a When clause describing the
  triggering action or event, or confirm the criterion is
  intentionally structured differently.
- **Known limitations:** Keyword presence only, not a grammatical
  parse.

### AC_THEN_PRESENT — Then clause present

- **Purpose:** Flag acceptance criteria missing a Then clause.
- **Checked:** Case-insensitive, word-boundary match for "then".
- **Confidence / false-positive / false-negative risk:** Same
  reasoning as AC_GIVEN_PRESENT, applied to "then".
- **Severity:** WARN only. **Blocks approval:** No.
- **PASS example:** As AC_GIVEN_PRESENT's PASS example.
- **WARN example:** "Given a user with 5 failed login attempts, when
  they retry."
- **Recommended BA action:** Add a Then clause describing the
  expected, verifiable outcome.
- **Known limitations:** Keyword presence only, not a grammatical
  parse.

### AC_MEASURABLE_THEN — Measurable Then condition

- **Purpose:** Flag acceptance criteria whose Then clause lacks a
  measurable or testable condition.
- **Checked:** The text between the first occurrence of "then" and
  whichever comes first — the end of that sentence, or the start of a
  new structural Given/When/Then group — for a number-plus-unit
  pattern, a comparison/threshold phrase, or a conditional connector —
  the exact same regex signals already used by
  `MISSING_ACCEPTANCE_CONDITION` (see above), reused rather than
  reimplemented. A sentence boundary is any of `.`/`!`/`?` that is not
  immediately adjacent to a digit (so a decimal value like "2.5
  seconds" is never split at its own decimal point). A new scenario is
  recognised by a capitalised "Given" or "When" that is
  *clause-initial* — immediately after a comma, immediately after
  sentence-ending punctuation, or at the very start of the text
  following "then" — never by the bare word appearing anywhere. This
  two-part boundary is deliberate and has gone through two rounds of
  correction: a plain "next Given/When" word match (an earlier version)
  cut the scan off at an ordinary lowercase "when"/"given" inside the
  Then clause's own genuine outcome text (e.g. "...locked when 5
  attempts occur...", "...shall be given a discount of at least
  10%..."); a subsequent Given-only, unanchored version then matched
  any capitalised "Given" appearing anywhere in the text, including as
  an ordinary word inside the Then clause itself (e.g. a "Given Name"
  form-field label), and separately never recognised a genuine second
  scenario introduced by "When" instead of "Given". Requiring both
  capitalisation *and* clause-initial position, and checking for either
  keyword, closes both gaps without reopening the original one. If no
  "then" is found at all, this rule reports WARN independently of
  `AC_THEN_PRESENT` — the two are separate structural facts and are
  never merged into one finding.
- **Confidence:** Medium — the same reasoning as
  `MISSING_ACCEPTANCE_CONDITION`, applied to the text after "then"
  rather than the whole requirement.
- **False-positive risk:** High — inherited directly from the reused
  signals; a Then clause can be genuinely testable without matching
  any of the three patterns.
- **Severity:** WARN only. **Blocks approval:** No.
- **PASS example:** "...then the system shall lock the account within
  2 seconds."
- **WARN example:** "...then the system shall lock the account." (no
  number, threshold phrase, or conditional connector after "then").
- **Recommended BA action:** Add a measurable condition (a number,
  threshold phrase, or conditional connector) to the Then clause.
- **Known limitations:** Same as `MISSING_ACCEPTANCE_CONDITION` —
  highest false-positive rate in its lineage; many genuinely testable
  Then clauses are phrased without matching these specific patterns.
  The scan is bounded to the first Then clause's own sentence, so a
  measurable signal that appears only in a second Given/When/Then
  group, or only in trailing prose after the first scenario, correctly
  does not count as evidence for the first Then clause — including
  when that second group is only comma-separated rather than a new
  sentence, whether it is introduced by a clause-initial capitalised
  "Given" or "When". An ordinary capitalised word that happens to be
  "Given" or "When" but is *not* clause-initial (e.g. a "Given Name"
  form-field label inside the Then clause) is correctly left alone and
  does not truncate the scan. The one residual gap this leaves: a
  second scenario introduced with a *lowercase* "given"/"when" and no
  sentence-ending punctuation or comma before it (e.g. "...then nothing
  happens given C, when D, then the value is at least 5.", a run-on
  sentence with no separating comma at all) is not recognised as a
  boundary and could still leak that second scenario's measurable
  evidence into the first Then clause's result. This is considered an
  acceptable residual limitation rather than a fix target: it requires
  a specific, ungrammatical construction (no punctuation separating two
  clauses at all, combined with non-canonical lowercase capitalisation)
  that is unlikely in practice, and further tightening the heuristic
  risks reintroducing one of the false-negatives this rule has already
  been corrected for twice.

### Approval gating (acceptance criteria)

Identical rules to requirement approval gating: PASS approves directly;
WARN requires an explicit, separately recorded acknowledgement
(`warn_acknowledged_at`, `warn_acknowledged_by`) that is cleared by
every new validation run; FAIL blocks approval outright (unreachable
through the current four rules, but fully enforced at both the
application and database layers); NOT_VALIDATED also blocks approval
outright, enforced the same way. `pending`, `approved`, and `rejected`
are one-way terminal states here too — approving or rejecting an
acceptance criterion is only permitted while it is `pending`, and an
already-decided criterion returns a 409 conflict rather than being
silently re-approved or re-rejected. Approving, rejecting, or editing
an acceptance criterion never changes its parent requirement's own
`review_status`.

If a criterion is ever left `not_validated` — for example because
validation raised after the criterion record was already committed —
`POST /acceptance-criteria/{id}/validate` re-runs the four
deterministic rules on demand, mirroring the equivalent
`POST /requirements/{id}/validate` endpoint in Module 1. This is a
recovery path only: it never calls the AI and never changes
`current_text`. Like Module 1's endpoint, it is restricted to `pending`
criteria and returns 409 for an already-approved or already-rejected
one, for the same reason described above for requirements — this
costs the recovery path nothing, since a criterion can only ever be
stranded at `not_validated` while it is still `pending` (a
`not_validated` criterion can never become `approved` in the first
place).

## Known limitations of the validator as a whole

- Duplicate detection is text-similarity based, not semantic.
- Ambiguous wording relies on a fixed term list.
- Missing acceptance condition has the highest false-positive rate in
  the rule set.
- Missing actor relies on a fixed pattern/role list, not a full
  grammatical parse.
- Possible contradiction is the weakest rule: high false positives,
  very high false negatives, and is presented as a prompt for
  judgement, not a reliable contradiction detector.
- No rule in this set determines business correctness.
- Document-scoped comparison (`DUPLICATE_NEAR`, `POSSIBLE_CONTRADICTION`)
  cannot include manually authored requirements, which have no
  resolvable source document under the current schema.
