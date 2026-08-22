# Module 1 Notes — AI Requirements Analyst

Interview-preparation notes for Module 1 of the AI Requirements &
Traceability Workbench. Covers everything built through Milestone 4
(human review workflow).

## What Module 1 does

Module 1 takes messy, unstructured stakeholder text (meeting notes, an
email, a rambling paragraph) and turns it into a reviewed, approved
catalogue of requirements. The pipeline is: paste text → AI extracts
candidate requirements → a deterministic rule engine checks each one
→ a human analyst reviews the evidence and the checks → the analyst
edits, approves, or rejects. Nothing becomes "approved" without a
human decision.

## What the AI does

The AI (Anthropic API) reads the source text once and proposes
candidate requirements. For each candidate it returns a cleaned-up
requirement statement and a verbatim quote from the source text that
justifies it. That's the entire job — it never scores quality, never
decides pass/fail, and never approves anything. The application
independently verifies the quote actually appears in the source text
before trusting anything the model returned.

## What the deterministic validator does

Five fixed, code-based rules run against every requirement: near-duplicate
detection, ambiguous wording, missing acceptance condition, missing
actor, and possible contradiction. Each produces PASS, WARN, or FAIL
with a plain-language explanation. It exists as a separate layer
specifically so requirement quality isn't just "whatever the AI says
looks fine" — it's a fixed, inspectable, repeatable set of checks that
behave the same way every time, which an AI judgment call cannot
promise.

## What the human does

The analyst is the only one who can approve or reject a requirement.
Given a requirement, they can see the AI's original text, the exact
source quote it came from, the validation results, and the full edit
history in one screen. They can edit the text (which re-runs
validation automatically), approve it (blocked if FAIL, requires an
explicit acknowledgement if WARN), or reject it (always allowed, never
deletes anything).

## What happens when a requirement is edited

Editing does not overwrite the previous validation result — it creates
a brand new validation run and leaves the old one in the database.
This matters for two reasons: first, the AI's original extraction and
quote are separately stored and never touched by an edit, so "what did
the AI actually say" is always answerable; second, keeping every past
validation run means the system can show *how* a requirement's quality
changed over time, which is exactly the kind of audit trail a real
delivery process would expect.

## What was difficult / genuinely unclear

The trickiest part was making the edit-then-revalidate sequence
atomic without touching the frozen validation engine. The existing
`run_validation()` function already owns its own commit/rollback
boundary. Rather than wrapping it in a second transaction (which the
project's architecture rules didn't want), I staged the edit-history
row and the text change on the same database session *before* calling
`run_validation()` and let its own commit/rollback cover both — so a
failed validation run correctly leaves no partial edit behind, without
changing a single line of frozen code. Getting that ordering right
took a test that deliberately forces a rule to fail, to prove nothing
partial was left in the database.

## How it was tested

34 new automated tests were added covering: editing (creation of edit
records, correct old/new text, re-validation, history preservation,
blocking edits on approved/rejected requirements, and atomic rollback
on a forced validation failure), approval (PASS approves cleanly, WARN
blocked without acknowledgement and allowed with it, FAIL always
blocked, approval never creates a new validation run), rejection
(always allowed, nothing deleted), and the composite review endpoint
(requirement, evidence, validation results, and edit history all
returned together, with the raw AI response never exposed). All 142
pre-existing tests continue to pass unchanged — 176 total, 0 failures.

## How I would explain Module 1 in an interview

"I built a workflow where AI drafts requirements from messy notes, but
the AI never gets the final say. A separate, fixed set of rules checks
each requirement — things like 'is this a duplicate,' 'is the wording
too vague,' 'is there a measurable condition' — and flags problems
without pretending to be a business expert. Then a human reviews the
evidence: what the AI actually extracted, the exact sentence it came
from, and what the rules found. Only the human can approve or reject.
If they edit something, the system re-checks it automatically and
keeps the old check result too, so you can always see what changed and
why. The point I wanted to demonstrate is that AI accelerates the
drafting work, but a person — backed by consistent, explainable rules
— still owns the decision."
