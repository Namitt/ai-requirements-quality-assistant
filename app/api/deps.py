from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy.orm import Session, sessionmaker

from app.db import get_engine
from app.extraction import ExtractionAPIError
from app.extraction.client import AnthropicExtractionClient, ExtractionClient
from app.extraction.gemini_client import GeminiExtractionClient

_engine = get_engine()
_SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)

# Centralised provider dispatch - this is the only place in the application
# that decides which AI provider serves a request. Individual clients never
# check AI_PROVIDER themselves, and no other module branches on it.
_DEFAULT_PROVIDER = "anthropic"
_SUPPORTED_PROVIDERS = ("anthropic", "gemini")


def get_db_session() -> Iterator[Session]:
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_extraction_client() -> ExtractionClient:
    provider = os.environ.get("AI_PROVIDER", _DEFAULT_PROVIDER).strip().lower()

    if provider == "anthropic":
        return AnthropicExtractionClient()
    if provider == "gemini":
        return GeminiExtractionClient()

    # An unrecognised AI_PROVIDER is a deployment-time misconfiguration, not
    # a per-request/per-user credential gap like a missing API key - every
    # extraction-touching request will fail identically until it's fixed,
    # so raising immediately here (rather than deferring into a client's
    # complete(), the way a missing API key is deferred) is appropriate:
    # there is no real SDK client construction with side effects to avoid
    # triggering early, just a string comparison. Never silently falls back
    # to a default provider - that would hide the typo instead of
    # surfacing it.
    raise ExtractionAPIError(
        f"Unsupported AI_PROVIDER '{provider}'. Supported values: "
        f"{', '.join(_SUPPORTED_PROVIDERS)}."
    )
