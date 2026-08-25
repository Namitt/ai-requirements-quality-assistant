from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

import httpx

DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"

# Unset (None) by default, which preserves the exact real-HTTP behaviour this
# module has always had. The public demo deployment is the only caller that
# ever sets this - to a per-session fastapi.testclient.TestClient bound to
# that session's own in-process FastAPI app - via use_test_client() below.
# A ContextVar (not a plain module-level variable) is used deliberately: it
# is scoped to the current context rather than being shared global mutable
# state, so it cannot leak between independent overrides.
_test_client_override: ContextVar[httpx.Client | None] = ContextVar(
    "_test_client_override", default=None
)


@contextmanager
def use_test_client(client: httpx.Client) -> Iterator[None]:
    """Route every api_client call made inside this block through `client`
    (a fastapi.testclient.TestClient, or any httpx.Client-compatible object)
    instead of a real HTTP request. Restores the previous behaviour - real
    HTTP, or whatever override was active before - on exit, even if the
    block raises.
    """
    token = _test_client_override.set(client)
    try:
        yield
    finally:
        _test_client_override.reset(token)


# Same ContextVar-scoped pattern as _test_client_override above, for the
# same reason: the public demo is the only caller that ever sets this, and a
# ContextVar keeps it from leaking into anything else running in the same
# process. This does not call or block any API route itself - it only lets
# a rendering layer (app/ui/streamlit_app.py) decide whether to offer a
# control that would trigger one, so the canonical two-process app's own
# behaviour is completely unaffected (the default is "not disabled").
_ai_drafting_disabled: ContextVar[bool] = ContextVar("_ai_drafting_disabled", default=False)


@contextmanager
def disable_ai_drafting() -> Iterator[None]:
    """Inside this block, ai_drafting_disabled() reports True. Intended for
    a UI layer to hide/disable AI-drafting controls (never for api_client
    itself to block a call) - see render_acceptance_criteria_section's use
    of ai_drafting_disabled() in app/ui/streamlit_app.py.
    """
    token = _ai_drafting_disabled.set(True)
    try:
        yield
    finally:
        _ai_drafting_disabled.reset(token)


def ai_drafting_disabled() -> bool:
    return _ai_drafting_disabled.get()


class APIClientError(RuntimeError):
    """Raised whenever a call to the backend API fails or returns an error.

    Carries a message that is already safe to show to a non-technical user -
    callers should never need to inspect the original exception.
    """


def _base_url() -> str:
    return os.environ.get("API_BASE_URL", DEFAULT_API_BASE_URL)


def _request(method: str, path: str, **kwargs: Any) -> Any:
    override = _test_client_override.get()
    try:
        if override is not None:
            # No timeout kwarg here: this is an in-process call (e.g. a
            # fastapi.testclient.TestClient), not a real network request,
            # and Starlette's TestClient deprecates/rejects the argument -
            # network timeouts have no meaning for an in-process ASGI call.
            response = override.request(method, path, **kwargs)
        else:
            url = f"{_base_url()}{path}"
            response = httpx.request(method, url, timeout=60.0, **kwargs)
    except httpx.RequestError as exc:
        raise APIClientError(
            "Could not reach the requirements API. Check that the backend "
            "is running and try again."
        ) from exc

    if response.status_code >= 400:
        detail = None
        try:
            detail = response.json().get("detail")
        except Exception:
            detail = None
        raise APIClientError(detail or "The API returned an unexpected error.")

    return response.json()


def extract_requirements(raw_text: str, title: str | None = None) -> dict:
    return _request("POST", "/extractions", json={"raw_text": raw_text, "title": title})


def get_extraction_run(extraction_run_id: int) -> dict:
    return _request("GET", f"/extraction-runs/{extraction_run_id}")


def list_extraction_runs() -> list[dict]:
    return _request("GET", "/extraction-runs")


def get_requirements_summary() -> list[dict]:
    return _request("GET", "/requirements/summary")


def replay_extraction(extraction_run_id: int) -> dict:
    return _request("POST", f"/extraction-runs/{extraction_run_id}/replay")


def validate_requirement(requirement_id: int) -> dict:
    return _request("POST", f"/requirements/{requirement_id}/validate")


def get_requirement_review(requirement_id: int) -> dict:
    return _request("GET", f"/requirements/{requirement_id}/review")


def patch_requirement(requirement_id: int, current_text: str) -> dict:
    return _request(
        "PATCH", f"/requirements/{requirement_id}", json={"current_text": current_text}
    )


def approve_requirement(requirement_id: int, acknowledge_warning: bool = False) -> dict:
    return _request(
        "POST",
        f"/requirements/{requirement_id}/approve",
        json={"acknowledge_warning": acknowledge_warning},
    )


def reject_requirement(requirement_id: int) -> dict:
    return _request("POST", f"/requirements/{requirement_id}/reject")


def draft_acceptance_criteria(requirement_id: int) -> dict:
    return _request("POST", f"/requirements/{requirement_id}/acceptance-criteria")


def list_acceptance_criteria(requirement_id: int) -> list[dict]:
    return _request("GET", f"/requirements/{requirement_id}/acceptance-criteria")


def replay_acceptance_criteria(extracted_acceptance_criterion_id: int) -> dict:
    return _request(
        "POST",
        f"/extracted-acceptance-criteria/{extracted_acceptance_criterion_id}/replay",
    )


def get_acceptance_criteria_review(acceptance_criterion_id: int) -> dict:
    return _request("GET", f"/acceptance-criteria/{acceptance_criterion_id}/review")


def patch_acceptance_criteria(acceptance_criterion_id: int, current_text: str) -> dict:
    return _request(
        "PATCH",
        f"/acceptance-criteria/{acceptance_criterion_id}",
        json={"current_text": current_text},
    )


def approve_acceptance_criteria(
    acceptance_criterion_id: int, acknowledge_warning: bool = False
) -> dict:
    return _request(
        "POST",
        f"/acceptance-criteria/{acceptance_criterion_id}/approve",
        json={"acknowledge_warning": acknowledge_warning},
    )


def reject_acceptance_criteria(acceptance_criterion_id: int) -> dict:
    return _request("POST", f"/acceptance-criteria/{acceptance_criterion_id}/reject")
