from __future__ import annotations

import httpx
import pytest

from app.ui import api_client
from app.ui.api_client import APIClientError


class _FakeResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_extract_requirements_success(monkeypatch):
    captured = {}

    def fake_request(method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return _FakeResponse(201, {"id": 1, "extracted_requirements": []})

    monkeypatch.setattr(httpx, "request", fake_request)

    result = api_client.extract_requirements("some text", title="T")

    assert result == {"id": 1, "extracted_requirements": []}
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/extractions")
    assert captured["json"] == {"raw_text": "some text", "title": "T"}


def test_request_raises_on_network_error(monkeypatch):
    def fake_request(method, url, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "request", fake_request)

    with pytest.raises(APIClientError) as excinfo:
        api_client.extract_requirements("some text")

    assert "backend" in str(excinfo.value).lower()


def test_request_raises_on_api_error_with_detail(monkeypatch):
    def fake_request(method, url, **kwargs):
        return _FakeResponse(502, {"detail": "The AI extraction service could not be reached."})

    monkeypatch.setattr(httpx, "request", fake_request)

    with pytest.raises(APIClientError) as excinfo:
        api_client.extract_requirements("some text")

    assert "could not be reached" in str(excinfo.value)


def test_request_raises_generic_message_when_detail_missing(monkeypatch):
    def fake_request(method, url, **kwargs):
        return _FakeResponse(500, {})

    monkeypatch.setattr(httpx, "request", fake_request)

    with pytest.raises(APIClientError):
        api_client.extract_requirements("some text")


def test_get_requirement_review_success(monkeypatch):
    captured = {}

    def fake_request(method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        return _FakeResponse(200, {"requirement": {"id": 5}})

    monkeypatch.setattr(httpx, "request", fake_request)

    result = api_client.get_requirement_review(5)

    assert result == {"requirement": {"id": 5}}
    assert captured["method"] == "GET"
    assert captured["url"].endswith("/requirements/5/review")


def test_patch_requirement_sends_current_text(monkeypatch):
    captured = {}

    def fake_request(method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return _FakeResponse(200, {"id": 5, "current_text": "New text"})

    monkeypatch.setattr(httpx, "request", fake_request)

    api_client.patch_requirement(5, "New text")

    assert captured["method"] == "PATCH"
    assert captured["url"].endswith("/requirements/5")
    assert captured["json"] == {"current_text": "New text"}


def test_approve_requirement_sends_acknowledge_warning(monkeypatch):
    captured = {}

    def fake_request(method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return _FakeResponse(200, {"id": 5, "review_status": "approved"})

    monkeypatch.setattr(httpx, "request", fake_request)

    api_client.approve_requirement(5, acknowledge_warning=True)

    assert captured["method"] == "POST"
    assert captured["url"].endswith("/requirements/5/approve")
    assert captured["json"] == {"acknowledge_warning": True}


def test_approve_requirement_defaults_acknowledge_warning_false(monkeypatch):
    captured = {}

    def fake_request(method, url, **kwargs):
        captured["json"] = kwargs.get("json")
        return _FakeResponse(200, {"id": 5, "review_status": "approved"})

    monkeypatch.setattr(httpx, "request", fake_request)

    api_client.approve_requirement(5)

    assert captured["json"] == {"acknowledge_warning": False}


def test_reject_requirement_sends_correct_request(monkeypatch):
    captured = {}

    def fake_request(method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        return _FakeResponse(200, {"id": 5, "review_status": "rejected"})

    monkeypatch.setattr(httpx, "request", fake_request)

    api_client.reject_requirement(5)

    assert captured["method"] == "POST"
    assert captured["url"].endswith("/requirements/5/reject")


def test_validate_requirement_sends_correct_request(monkeypatch):
    captured = {}

    def fake_request(method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        return _FakeResponse(200, {"requirement": {}, "validation_run": {}})

    monkeypatch.setattr(httpx, "request", fake_request)

    api_client.validate_requirement(5)

    assert captured["method"] == "POST"
    assert captured["url"].endswith("/requirements/5/validate")


def test_list_extraction_runs_sends_correct_request(monkeypatch):
    captured = {}

    def fake_request(method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        return _FakeResponse(200, [{"id": 1, "mode": "live"}])

    monkeypatch.setattr(httpx, "request", fake_request)

    result = api_client.list_extraction_runs()

    assert result == [{"id": 1, "mode": "live"}]
    assert captured["method"] == "GET"
    assert captured["url"].endswith("/extraction-runs")


def test_replay_extraction_sends_correct_request(monkeypatch):
    captured = {}

    def fake_request(method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        return _FakeResponse(201, {"id": 2, "mode": "replay"})

    monkeypatch.setattr(httpx, "request", fake_request)

    result = api_client.replay_extraction(1)

    assert result == {"id": 2, "mode": "replay"}
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/extraction-runs/1/replay")


def test_base_url_defaults_and_env_override(monkeypatch):
    monkeypatch.delenv("API_BASE_URL", raising=False)
    assert api_client._base_url() == api_client.DEFAULT_API_BASE_URL

    monkeypatch.setenv("API_BASE_URL", "http://example.test:9000")
    assert api_client._base_url() == "http://example.test:9000"
