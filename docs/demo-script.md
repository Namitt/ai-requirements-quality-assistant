# Demo Script (Five Minutes)

## Presenter cheat sheet — result meanings

- **PASS** — No configured check found a problem. Not a claim of
  correctness. No acknowledgement needed; approval can proceed
  directly.
- **WARN** — A potential issue was detected; requires analyst
  judgement. Approving it requires an explicit acknowledgement action,
  recorded on the requirement (who + when) — approval alone is never
  treated as proof the analyst saw the warning.
- **FAIL** — A high-confidence issue that blocks approval outright
  until fixed. Only the high-confidence tier of near-duplicate
  detection can produce FAIL in this version.

## Fixture requirement for this script

The demo source text must extract into a small set of candidate
requirements that includes: at least one clean requirement (PASS), at
least one requirement with an ambiguous or missing-condition wording
problem (WARN), and one near-duplicate pair (FAIL on the second of the
pair). This is planned into the fixture design, not left to chance
during the live extraction.

## Fallback if there is no network / no API access

Switch to **replay mode** before the demo starts, or live on request:
replay re-runs a previously captured AI extraction through the exact
same validation, review, and approval pipeline, with no live API call.
State this plainly if it comes up — it is a deliberate design choice,
not a workaround being hidden.

## Flow

Source → AI extraction → validation → BA review → correction →
re-validation → human approval → traceability/audit.

1. **(0:00) Show the messy source.** A realistic, slightly rambling
   stakeholder note — nothing pre-cleaned.
2. **(0:20) Run extraction.** Live if network/API is reliable in the
   room, replay otherwise. Candidates are created, each automatically
   paired with a reviewable requirement, and validation runs
   immediately — the table appears already showing a mix of PASS,
   WARN, and FAIL.
3. **(0:50) WARN case — acknowledge and approve as-is.** Point at the
   ambiguous-wording WARN. Explain in one sentence why it's a WARN,
   not a FAIL, tying back to the confidence × significance framework.
   Click **Acknowledge**, then **Approve** — call out that
   `warn_acknowledged_at`/`warn_acknowledged_by` are now recorded on
   the requirement, not just implied by the approval.
4. **(1:30) WARN case — correct instead.** Point at a second,
   different WARN requirement (e.g. missing acceptance condition).
   Edit the text live to add a measurable condition.
5. **(2:10) Re-validate.** Show the result change to PASS, and note
   that any prior acknowledgement would have been cleared by this new
   validation run. Approve normally — no acknowledgement needed for
   PASS.
6. **(2:40) FAIL case.** Point at the near-duplicate pair. Attempt to
   approve the second one — the action is blocked; read the reason
   aloud. Keep this brief: the point is to show the gate is real, not
   to resolve the duplicate live.
7. **(3:10) Traceability.** Click from an approved requirement back to
   the exact source sentence it came from.
8. **(3:40) Scroll back through the set.** Point out each card's own
   `validation_state`/`review_status` badges as you scroll — how many
   were approved directly, how many needed acknowledgement, and the
   one still blocked on FAIL. (Note if asked: `GET /requirements`
   already returns `origin`, `validation_state`, and `review_status`
   for every requirement at once — enough to build a single
   consolidated summary table — but that specific screen isn't built
   in the UI yet, only per-card display.)
9. **(4:20) One-line limitations note.** Name the weakest rule
   (possible contradiction) as a caveat, to show the limitations are
   known, not hidden.
10. **(4:45) Close.** AI accelerates drafting; deterministic rules and
    recorded human decisions are what actually gate approval.

## What this demo is deliberately not claiming

- Not claiming the validator understands business correctness.
- Not claiming AI-generated text is pre-validated or reliable on its
  own.
- Not claiming contradiction detection is reliable — if it comes up,
  describe it explicitly as a possible-contradiction heuristic.
- Not claiming the mix of PASS/WARN/FAIL results shown reflects
  real-world requirement quality — the fixture is deliberately
  constructed to demonstrate each outcome.
