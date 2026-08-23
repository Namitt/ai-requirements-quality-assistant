from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.extraction import (
    ExtractionAPIError,
    ExtractionParseError,
    SourceQuoteNotFoundError,
)
from app.acceptance_criteria import AcceptanceCriteriaParseError
from app.acceptance_criteria_engine import (
    AcceptanceCriteriaReplaySourceNotFoundError,
    AcceptanceCriteriaReplaySourceNotLiveError,
)
from app.extraction_engine import ReplaySourceNotFoundError, ReplaySourceNotLiveError
from app.validation_engine import ValidationConfigurationError

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    # Known, documented extraction failure modes: the AI service could not
    # be reached, or returned something that could not be used. The client
    # request itself was fine, so these map to 502 (bad upstream response)
    # rather than 4xx or a generic 500.
    @app.exception_handler(ExtractionAPIError)
    async def handle_extraction_api_error(request: Request, exc: ExtractionAPIError):
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    @app.exception_handler(ExtractionParseError)
    async def handle_extraction_parse_error(request: Request, exc: ExtractionParseError):
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    @app.exception_handler(SourceQuoteNotFoundError)
    async def handle_source_quote_not_found(request: Request, exc: SourceQuoteNotFoundError):
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    # Replay was asked to reproduce a run that either doesn't exist, or
    # isn't eligible to be replayed (already a replay, not a live run).
    @app.exception_handler(ReplaySourceNotFoundError)
    async def handle_replay_source_not_found(request: Request, exc: ReplaySourceNotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ReplaySourceNotLiveError)
    async def handle_replay_source_not_live(request: Request, exc: ReplaySourceNotLiveError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    # Acceptance-criteria drafting: the model response could not be parsed
    # into a single criterion - same treatment as ExtractionParseError above.
    @app.exception_handler(AcceptanceCriteriaParseError)
    async def handle_acceptance_criteria_parse_error(
        request: Request, exc: AcceptanceCriteriaParseError
    ):
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    # Acceptance-criteria replay: the same not-found/not-live distinction as
    # extraction replay, applied to extracted_acceptance_criteria rows.
    @app.exception_handler(AcceptanceCriteriaReplaySourceNotFoundError)
    async def handle_ac_replay_source_not_found(
        request: Request, exc: AcceptanceCriteriaReplaySourceNotFoundError
    ):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(AcceptanceCriteriaReplaySourceNotLiveError)
    async def handle_ac_replay_source_not_live(
        request: Request, exc: AcceptanceCriteriaReplaySourceNotLiveError
    ):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    # Genuine server-side misconfiguration (the validation rule catalog is
    # incomplete) - not the client's fault, not an upstream AI problem.
    @app.exception_handler(ValidationConfigurationError)
    async def handle_validation_configuration_error(
        request: Request, exc: ValidationConfigurationError
    ):
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    # Catch-all for anything not explicitly anticipated. Logged in full
    # server-side; the client only ever sees a generic message, never a
    # stack trace or exception internals.
    @app.exception_handler(Exception)
    async def handle_unexpected_exception(request: Request, exc: Exception):
        logger.exception("Unhandled exception while processing request")
        return JSONResponse(
            status_code=500, content={"detail": "An unexpected internal error occurred."}
        )
