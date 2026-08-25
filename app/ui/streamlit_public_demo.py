"""Public-demo Streamlit entrypoint.

This is a deployment-specific PACKAGING of the same application, not a
redesign of it. The canonical, designed, and tested architecture remains
two separate processes - FastAPI backend + Streamlit UI as an HTTP client
- runnable locally exactly as documented in README.md and
app/ui/streamlit_app.py. This file exists only because Streamlit
Community Cloud can host a single process, and packages the same real
application to fit that constraint:

  Streamlit (this file)
      |
      | in-process, via fastapi.testclient.TestClient
      v
  a fresh FastAPI() instance per Streamlit session
      | (the same real routers/exception handlers app.main.app uses)
      v
  a fresh sqlite:///:memory: database per Streamlit session
      | (StaticPool + check_same_thread=False; same schema/models)
      v
  seeded once per session from app/ui/public_demo_fixture.py - a genuine
  captured snapshot of real AI provider output, never a live call

No AI provider key is read, needed, or possible to use here: no route
reachable from this page ever resolves `get_extraction_client()` for a
key-bearing action against this session's own data. The one control that
would otherwise reach it - the pre-existing "Draft Acceptance Criteria"
button in app/ui/streamlit_app.py - is disabled specifically for this
entrypoint via `api_client.disable_ai_drafting()` below, so a recruiter
can never trigger a real (or, if a deployment administrator ever
misconfigures a provider key into this app's secrets, billable) provider
call from a public page. This is a public-demo-specific toggle, read by a
single `if` in `render_acceptance_criteria_section` - it changes nothing
about the canonical two-process app's own behaviour, where the control
remains fully active by default.

Nothing in app/api/*, app/models.py, app/validation_engine.py, any rule
module, or either extraction client is touched by this file - it only
composes already-existing, already-tested pieces.
"""

from __future__ import annotations

import fastapi as _fastapi_module
import streamlit as st
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db_session
from app.api.errors import register_exception_handlers
from app.api.routes.acceptance_criteria import router as acceptance_criteria_router
from app.api.routes.extraction import router as extraction_router
from app.api.routes.requirements import router as requirements_router
from app.db import Base
from app.seed import seed_validation_rules
from app.ui import api_client
from app.ui.public_demo_fixture import seed_fixture
from app.ui.streamlit_app import (
    render_audit_summary_section,
    render_header,
    render_replay_section,
    render_results_section,
)

DISCLOSURE = (
    "This public demo uses a captured AI extraction replay so it can be used "
    "safely without an API key or live model call. Every requirement, "
    "validation result, and acceptance criterion shown was genuinely produced "
    "once by a real Google Gemini call and captured for deterministic replay "
    "- nothing on this page ever contacts a live AI provider."
)


def _build_session_bundle() -> dict:
    """Everything one Streamlit session needs, built once and cached in
    st.session_state: its own FastAPI app instance, its own in-memory
    SQLite database, and a TestClient bound to both. Mirrors exactly the
    construction empirically proven in the Stage 1 standalone proof and
    the Stage 4 real-Streamlit-runtime isolation proof.

    `getattr(_fastapi_module, "FastAPI")()` is used instead of a literal
    `FastAPI()` call deliberately: Streamlit 1.62 was empirically observed
    (Stage 4) to statically scan the run target's source for the literal
    substring "FastAPI(" and attempt to hand off serving to it via
    uvicorn's ASGI-app loader, even when that construction is unreachable
    at import time - this indirection is the same verified-safe technique
    from that proof, not a new workaround.
    """
    fastapi_app = getattr(_fastapi_module, "FastAPI")()
    register_exception_handlers(fastapi_app)
    fastapi_app.include_router(extraction_router)
    fastapi_app.include_router(requirements_router)
    fastapi_app.include_router(acceptance_criteria_router)
    # Deliberately no /health here: it is registered directly on
    # app.main.app, not on any of the three routers above (a Stage 1
    # finding), and is not needed by this page.

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_factory() as seed_session:
        seed_validation_rules(seed_session)
        refs = seed_fixture(seed_session)

    def override_get_db_session():
        session: Session = session_factory()
        try:
            yield session
        finally:
            session.close()

    fastapi_app.dependency_overrides[get_db_session] = override_get_db_session

    # TestClient is the synchronous, httpx.Client-compatible wrapper around
    # an in-process ASGI transport (a plain httpx.Client(transport=
    # ASGITransport(...)) does not work - it only implements the async
    # transport interface; see the Stage 1 finding). Entered once and kept
    # open for this session's whole lifetime, exactly as Stage 4 proved
    # safe across many reruns.
    ctx = TestClient(fastapi_app)
    client = ctx.__enter__()

    return {
        "app": fastapi_app,
        "engine": engine,
        "session_factory": session_factory,
        "client": client,
        "_ctx": ctx,
        "refs": refs,
    }


def main() -> None:
    # st.cache_resource is deliberately never used here - it is shared
    # across ALL concurrent Streamlit sessions in one process, which would
    # silently recreate the exact cross-visitor data leak this whole
    # milestone exists to avoid. st.session_state is the only correct
    # place for per-session state (empirically proven in Stage 4).
    if "public_demo_bundle" not in st.session_state:
        st.session_state["public_demo_bundle"] = _build_session_bundle()
        # Seed the initially-displayed extraction run so meaningful demo
        # content is visible immediately, with zero clicks required.
        st.session_state["extraction_run_id"] = st.session_state[
            "public_demo_bundle"
        ]["refs"]["run1"]

    bundle = st.session_state["public_demo_bundle"]

    render_header()
    st.info(DISCLOSURE)

    with api_client.use_test_client(bundle["client"]), api_client.disable_ai_drafting():
        workflow_tab, audit_tab = st.tabs(["Workflow", "Audit & Traceability Summary"])

        with workflow_tab:
            render_replay_section()
            render_results_section()

        with audit_tab:
            render_audit_summary_section()


if __name__ == "__main__":
    main()
