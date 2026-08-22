# Known Limitations and Deliberate Scope Cuts

This document exists so the project never implies capabilities it does
not have. Every limitation here is either an inherent constraint of a
deterministic, explainable validator, or a deliberate scope decision
made to keep the project focused and interview-defensible.

## Validation limitations

- **Duplicate detection is text-similarity based, not semantic.**
  Paraphrased duplicates that share little vocabulary will not be
  caught. Only near-exact textual overlap reaches FAIL; everything
  else is WARN at best.
- **Document-scoped comparison excludes manually authored
  requirements.** `DUPLICATE_NEAR` and `POSSIBLE_CONTRADICTION` only
  compare requirements that can be traced back to a source document
  through their AI extraction record. A requirement added manually
  (`origin='manual'`) has no such record and is therefore never
  compared against other requirements by these two rules, in either
  direction. This is a schema-driven limitation of this version, not
  a decision to exempt manual requirements from quality checks
  generally — only from these two document-scoped ones.
- **Ambiguous wording detection relies on a fixed vocabulary list.**
  It has no contextual understanding — a listed term inside an
  otherwise precise sentence will still be flagged, and vague phrasing
  outside the list will be missed entirely.
- **Missing acceptance condition has the highest false-positive rate
  in the rule set.** Many legitimate, testable requirements do not
  contain a number, threshold phrase, or conditional connector and
  will still be flagged for review.
- **Missing actor detection is pattern-based, not a grammatical
  parse.** It recognises a small configured list of actor phrasings
  and will misjudge unusual but valid sentence structures.
- **Possible contradiction detection is the weakest rule in the set.**
  It only catches contradictions that manifest as a numeric or
  negation mismatch between two requirements with significant
  vocabulary overlap. It has a high false-positive rate and a very
  high false-negative rate, and is always presented as a possible
  contradiction requiring human judgement — never as a confirmed
  contradiction. A semantic or model-based contradiction detector was
  deliberately not built, to keep validation deterministic and
  explainable.
- **No rule determines business correctness.** PASS means no
  configured check found a problem — it is never a claim that a
  requirement is correct, complete, or ready for delivery in a
  business sense.

## AI extraction limitations

- AI extraction is non-deterministic. Running the same source text
  through a live extraction twice may produce different candidate
  requirements. Model name and prompt version are stored per
  extraction run for traceability, but this does not guarantee
  reproducibility — it only records what was used.
- AI is used only to extract candidate requirements from text. It does
  not validate, approve, or assess business correctness at any point
  in the workflow.

## Replay mode limitations

- Replay mode re-runs a previously captured AI result through the same
  validation and review pipeline. It demonstrates the deterministic
  and human-review parts of the system reliably, but it is not a live
  extraction — it does not prove the AI would produce the same output
  again, and is never presented as a new model call.

## Data limitations

- The fixture dataset used for demonstration and testing is small and
  synthetic. It is designed to plant a known set of requirement-quality
  problems for validator testing, not to represent a realistic volume
  or diversity of real-world requirements.

## Scope limitations

- **Single-user, local-first.** There is no authentication, no
  concept of multiple reviewers, and no access control. This is a
  deliberate scope decision, not an oversight — adding multi-user
  support would require an authorization model that is out of scope
  for a requirements-quality demonstration.
- **No FAIL override workflow.** A requirement with a FAIL result
  cannot be approved under any circumstances in this version, even
  though real BA workflows sometimes require approving a known defect
  for schedule reasons. This was deliberately left out to keep the
  approval gate simple and unambiguous; see `decisions-log.md`.
- **No integration with delivery tools** (e.g. Jira, Azure DevOps).
  Requirements produced here are not pushed anywhere; traceability and
  export beyond the application itself are out of scope.
- **No production security hardening.** This is a local demonstration
  tool, not a deployed service, and has not been evaluated against
  production security requirements.

## What this project is designed to demonstrate

This section describes design intent, not a verified outcome. It will
be revisited once the application is implemented and tested, to
confirm each claim actually holds in practice rather than assuming it
from the design alone.

- An explainable distinction between AI-generated content,
  deterministic validation, and human review/approval.
- A traceable path from source text to approved requirement.
- A validator whose confidence claims are intended to match its actual
  detection method, rule by rule.
- Deliberate, documented scope boundaries rather than unstated gaps.
