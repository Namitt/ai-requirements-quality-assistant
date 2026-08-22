from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session, sessionmaker

from app.db import get_engine
from app.extraction.client import AnthropicExtractionClient, ExtractionClient

_engine = get_engine()
_SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)


def get_db_session() -> Iterator[Session]:
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_extraction_client() -> ExtractionClient:
    return AnthropicExtractionClient()
