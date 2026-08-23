# Module 1 Notes — AI Requirements Analyst

Interview-preparation notes for Module 1 of the AI Requirements &
Traceability Workbench. Covers everything built through Milestone 6
(Replay Mode).

Module 2 (the Acceptance Criteria Assistant) has its own notes in
`module2-notes.md` — this file remains the historical record of
Module 1 only.

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

## The Streamlit UI (Milestone 5)

A single-page Streamlit app (`app/ui/streamlit_app.py`) turns the
Module 1 API into something a non-technical analyst can actually use:
paste text → click Extract → see each requirement's AI draft, source
evidence, and validation results → edit/approve/reject inline.

## How it communicates with FastAPI

Streamlit never talks to the database, the extraction engine, or
Anthropic directly. Every action goes through a small API client
(`app/ui/api_client.py`) that makes plain HTTP calls to the existing
FastAPI endpoints — the same ones already covered by 176 backend
tests. The chain is always `Streamlit → FastAPI → extraction/validation
engines → database`. The API base URL comes from an `API_BASE_URL`
environment variable (defaulting to `http://127.0.0.1:8000` for local
development) — never hardcoded, and the Anthropic key never leaves the
server side.

## Why Streamlit

It's a pure-Python UI library that renders the workflow directly from
the existing Pydantic response shapes, with no separate frontend
build, no JavaScript, and no new state-management framework — a good
fit for a project whose point is the backend workflow, not the UI
technology. A React/Vite frontend (the option originally named in
`architecture.md`) was considered and rejected for this milestone
specifically because it would have meant weeks of unrelated frontend
engineering to demonstrate the same backend story — see the
decisions-log entry for the full reasoning.

## Why the API remains the source of truth

The UI never calculates a validation state, an approval rule, or an
edit history — it only displays what the API returns and re-fetches
after every action (`GET /requirements/{id}/review`). Streamlit's
`session_state` is used only to remember *which* extraction run and
*which* requirement's edit box is open — never a cached copy of
requirement data. This means the UI can never drift out of sync with
the database, and it can never accidentally become a second place
where approval or validation rules are decided.

## What the user sees during extraction

Two distinct, sequential steps, deliberately not merged into one:
first a spinner reading "AI extraction in progress," then — only once
extraction succeeds — a second, separately labelled spinner reading
"Running deterministic validation... independent, fixed rule checks,
not the AI." Every requirement card repeats this separation visually,
with its own "🤖 AI-drafted requirement" block followed by its own
"🔎 Deterministic validation — checked independently of the AI" block.

## How validation is presented

Each of the five rule results is shown individually (rule code,
PASS/WARN/FAIL, the plain-language message, and the recommended action
where there is one) — never just a single pass/fail badge with no
explanation.

## How edit/re-validation works

Editing opens an inline text box seeded with the current text. Saving
calls `PATCH /requirements/{id}`, which the backend re-validates
automatically; the UI then re-fetches the requirement so the analyst
immediately sees the new validation state — it never assumes an edit
fixed anything.

## How approval/rejection works

PASS shows a plain Approve button. WARN shows a required
acknowledgement checkbox that must be ticked before the Approve button
even becomes clickable — the UI cannot set `acknowledge_warning=true`
on its own. FAIL shows a disabled Approve button with the reason
written next to it. Reject is always available and never deletes
anything.

## Genuine implementation difficulty this milestone

Streamlit reruns the entire script on every interaction, so
"remembering" which requirement's edit box is open, or that an
extraction just completed, has to live in `session_state` rather than
ordinary Python variables. Getting the "Load Demo Scenario" button to
correctly pre-fill the text area required using Streamlit's `on_click`
callback (which runs *before* the rerun's widgets are drawn) rather
than a plain post-click check — the more obvious approach silently
fails to update the text area on the same click.

## How the Streamlit layer was tested

11 new tests cover `api_client.py` in isolation (successful calls, a
simulated network failure, a backend error response with and without
a `detail` field, and that each function sends the correct method,
path, and JSON body) — all via `monkeypatch` on `httpx.request`, no
real network calls. Streamlit's own widget-level behaviour was not
unit-tested; instead the app was smoke-tested by actually launching it
(`streamlit run`) and confirming it starts cleanly and serves a page,
since pixel/widget-level tests for a page this thin would add
complexity without meaningfully increasing confidence. All 176
pre-existing tests continue to pass unchanged — 187 total, 0 failures.

## Replay mode (Milestone 6)

### What replay does

Replay re-runs a *previously captured* extraction — the same
requirement text, the same source evidence, the same model and prompt
version on record — through validation and human review again,
without contacting the AI service a second time. It produces a brand
new extraction run and a brand new set of requirements (fresh IDs,
fresh review state), so it can be edited, approved, or rejected
independently of the original, but it never re-asks the AI anything.

### Why it exists

The application needs to be demonstrable — in an interview, on a
laptop with no internet, or with no API key configured — without that
being a lesser or fake version of the product. Replay makes that
possible honestly: it's not a canned screenshot or a mocked response,
it's the same database-backed pipeline every other requirement goes
through, just fed from a prior AI result instead of a new one.

### How it differs from a live extraction

A live extraction calls the AI, gets a fresh answer, and stores that
answer as a new immutable record. A replay never calls the AI at all —
it copies the requirement text, the source quote, and the source
span from an existing *live* run's records into new rows. The copy is
only ever taken from a live run; a replay of a replay is rejected,
so there's always exactly one AI-original record behind any replay,
no matter how many times it's replayed.

### Still goes through the same validation and review

A replayed requirement is not treated as pre-approved or pre-checked.
The moment its copy is created, it runs through the exact same
deterministic validation engine as a live requirement, and it starts
out `pending` in review status like any other requirement — it still
needs a human to approve or reject it. In practice this also means a
replay is a genuine, honest test of validation: in the demo scenario
used for verification, a replayed requirement that duplicated another
requirement already in that document was correctly flagged FAIL by
the near-duplicate rule, exactly as it would be for a live extraction.

### How it's exposed in the UI

The Streamlit app gained one new control, "Replay a previous
extraction," sitting alongside the existing paste-and-extract input.
It lists live extraction runs to choose from and, on request, replays
the selected one. From that point on, the replayed run's requirements
appear in exactly the same requirement cards, with exactly the same
edit/approve/reject controls, as a live extraction's results — no
second review screen was built, because none was needed.

### How it was tested

19 new backend tests cover `run_replay()` directly: correct run
metadata (mode, `replayed_from_run_id`, model/prompt version copied),
exact copying of requirement text and source evidence with fresh
database IDs, the original live run left completely untouched,
automatic validation of every replayed requirement, rejection of a
non-existent or already-replayed source run, and that no live
extraction client is ever invoked — proved by running replay with no
`ANTHROPIC_API_KEY` set at all. 6 new API tests cover the same
behaviour through the HTTP layer (a new `GET /extraction-runs` listing
endpoint and `POST /extraction-runs/{id}/replay`), and 2 new tests
cover the UI's API client wrappers. All pre-existing tests continue to
pass unchanged — 214 total, 0 failures. The Streamlit app was also
smoke-tested against a real running backend with a real (fake-client)
live extraction seeded into the database, including actually calling
the replay endpoint end-to-end and confirming the deterministic
validator correctly flagged the resulting duplicate.

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

"I also added a replay mode so I can demonstrate the whole pipeline
without needing a live AI call in the room — it re-runs a previously
captured extraction through the same validation and review steps,
which matters for an offline demo but also, more importantly, proves
the deterministic checks aren't just decoration around the AI call —
they're a real, independent layer that runs the same way every time,
regardless of where the requirement text came from."
