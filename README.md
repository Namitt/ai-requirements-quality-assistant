# AI Requirements & Traceability Workbench

A portfolio project demonstrating a deliberate three-stage workflow for
software requirements: **AI drafts → deterministic rules validate →
a human decides.** The AI never validates or approves anything; a
fixed, inspectable set of rules is the sole authority on structural
quality, and every approval/rejection decision is made and recorded by
a human analyst.

Two modules exist on top of the same pattern:

- **Module 1 — Requirements.** Extract candidate requirements from raw
  source text, validate them deterministically, and let an analyst
  edit/approve/reject each one with full traceability back to the
  source text.
- **Module 2 — Acceptance Criteria.** For any requirement, draft a
  Given/When/Then acceptance criterion, validate its structure, and
  run it through the same edit/approve/reject review lifecycle,
  independently of the parent requirement's own status.

See `docs/architecture.md`, `docs/decisions-log.md`, and
`docs/validation-rules.md` for the full design rationale — this README
covers only what's needed to set the project up and run it.

## Architecture / components

| Layer | Choice |
|---|---|
| Backend | Python + FastAPI (`app/api/`, `app/main.py`) |
| Database | SQLite, one file (`requirements_quality.db`) |
| Data access | SQLAlchemy models (`app/models.py`) + Alembic migrations (`alembic/`) |
| AI provider | Anthropic API, used only for drafting (extraction / acceptance criteria), never for validation |
| Analyst UI | Streamlit (`app/ui/streamlit_app.py`), calls the FastAPI backend over HTTP |
| Validation | Deterministic rule modules (`app/rules/`), dispatched by `app/validation_engine.py` (requirements) and `app/acceptance_criteria_validation_engine.py` (acceptance criteria) |
| Testing | pytest (`tests/`) |

The FastAPI backend and the Streamlit UI are **two separate
processes** — the UI is a thin HTTP client of the API, not a shared
codebase running in-process.

## Prerequisites

- Python 3.10 or later (see `pyproject.toml`'s `requires-python`).
- An Anthropic API key, **only** if you want to exercise live AI
  drafting (extraction or acceptance-criteria generation). Everything
  else — validation, review, approval, replay mode, the test suite —
  works with no API key at all.

## Installation

This project does not currently install as a package (there is no
`[build-system]` in `pyproject.toml`, and `pip install -e .` does not
work as-is — see "Known limitations" below). Install its dependencies
directly instead, and run every command from the repository root so
Python can resolve the local `app`/`alembic` packages from the current
directory.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Reproduce the exact tested environment (recommended):
pip install -r requirements-lock.txt

# — or — install from the abstract version ranges instead:
pip install "sqlalchemy>=2.0,<3.0" "alembic>=1.13,<2.0" "pytest>=8.0,<9.0" \
            "anthropic>=0.40,<1.0" "fastapi>=0.110,<1.0" "uvicorn>=0.29,<1.0" \
            "httpx>=0.27,<1.0" "streamlit>=1.35,<2.0"
```

## Environment variables / configuration

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Only for live AI drafting | — (read directly by the `anthropic` SDK) | Authenticates extraction / acceptance-criteria drafting calls. Not needed for validation, review, approval, replay mode, or the test suite. |
| `ANTHROPIC_MODEL` | No | `claude-sonnet-5` | Overrides which Anthropic model is used for drafting (`app/extraction/client.py`). |
| `API_BASE_URL` | No | `http://127.0.0.1:8000` | Tells the Streamlit UI (a separate process) where the FastAPI backend is listening (`app/ui/api_client.py`). |

The database location itself is **not** environment-configurable in
this version — `app/db.py` hardcodes `sqlite:///requirements_quality.db`
(relative to wherever the process is started from), and `alembic.ini`'s
`sqlalchemy.url` must be kept in sync with it manually if you ever
change one.

## Database setup

Every schema change lives in `alembic/versions/`. From a fresh clone
(no `requirements_quality.db` file yet):

```bash
alembic upgrade head
```

This creates every table **and** seeds the `validation_rules` catalog
(migration `0004`) — both are required before any validate call will
work; skipping this step, or stopping at an older revision, is exactly
the failure mode `GET /health` (below) is designed to detect and
report.

To inspect or roll back:

```bash
alembic current           # show the applied revision
alembic downgrade -1      # roll back one migration
alembic upgrade head      # re-apply
```

## Running the FastAPI application

From the repository root, with the virtual environment active:

```bash
uvicorn app.main:app --reload
```

Then check `GET http://127.0.0.1:8000/health` — it returns `200
{"status": "ok"}` only when the database is reachable **and** the
`validation_rules` catalog is fully seeded; otherwise it returns `503`
with a message telling you what to fix (almost always: run `alembic
upgrade head`). Interactive API docs are served at `/docs`.

## Running the Streamlit UI

In a **second** terminal, with the backend already running and the
same virtual environment active:

```bash
streamlit run app/ui/streamlit_app.py
```

Set `API_BASE_URL` first if the backend isn't at the default
`http://127.0.0.1:8000`.

## Running the test suite

```bash
pytest
```

The test suite builds its own throwaway SQLite databases per test
(via `Base.metadata.create_all()` and, for `tests/test_migrations.py`,
real Alembic runs against a temp file) — it never touches your local
`requirements_quality.db`, and needs no Anthropic API key (AI calls are
faked in every test).

## Expected development workflow

1. Make a change.
2. If it touches the schema, add a new Alembic migration under
   `alembic/versions/` (see the existing `0001`–`0004` for this
   project's conventions: self-contained files, no imports from `app/`,
   `batch_alter_table` for SQLite `ALTER`-requiring changes, explicit
   `upgrade()`/`downgrade()` symmetry).
3. Add or update tests alongside the change — this project has no
   untested modules by convention.
4. Run `pytest` and confirm the full suite passes before considering
   the change done.
5. Update the relevant doc under `docs/` (`architecture.md`,
   `validation-rules.md`, `decisions-log.md`, or `limitations.md`) if
   the change affects behaviour those files describe.

## Known limitations

Full list in `docs/limitations.md`. Highlights:

- **Single-user, local-first.** No authentication, no multi-user
  access control — a deliberate scope decision, not an oversight.
- **Not evaluated against production security requirements** (no
  CORS policy, no rate limiting, no deployment hardening). This is a
  local demonstration tool.
- **`pip install -e .` does not work** — `pyproject.toml` has no
  `[build-system]`, and setuptools' automatic package discovery finds
  both `app` and `alembic` as ambiguous top-level packages. Every
  command in this README is run directly from the repository root
  instead, which works without installing the project itself.
- Deterministic validation rules are pattern/keyword based, not a
  grammatical parse — see `docs/validation-rules.md` for each rule's
  specific false-positive/false-negative profile.

## Current project scope

This is a portfolio/demonstration project, not a production service.
There is no Docker/container configuration, no CI pipeline, and no
production ASGI process configuration beyond the bare `uvicorn`
command above — see `docs/limitations.md`'s "Scope limitations" for
the complete, deliberate list of what was left out and why.

## Dependency locking

`requirements-lock.txt` is a `pip freeze` snapshot of the exact,
fully-resolved environment (direct and transitive) this project was
developed and tested against, generated with the project's existing
tooling (plain `pip`) rather than adopting a new dependency manager
(Poetry/uv) for a single-developer, single-environment project. See
`docs/decisions-log.md` for the full reasoning. `pyproject.toml`
remains the source of truth for the intended, abstract version ranges;
regenerate the lock file with `pip freeze > requirements-lock.txt`
after any intentional dependency change.
