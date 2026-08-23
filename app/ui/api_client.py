from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"


class APIClientError(RuntimeError):
    """Raised whenever a call to the backend API fails or returns an error.

    Carries a message that is already safe to show to a non-technical user -
    callers should never need to inspect the original exception.
    """


def _base_url() -> str:
    return os.environ.get("API_BASE_URL", DEFAULT_API_BASE_URL)


def _request(method: str, path: str, **kwargs: Any) -> Any:
    url = f"{_base_url()}{path}"
    try:
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
