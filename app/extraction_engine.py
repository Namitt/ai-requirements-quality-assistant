from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extraction import ExtractionError, SourceQuoteNotFoundError
from app.extraction.client import ExtractionClient
from app.extraction.parser import parse_response
from app.extraction.prompt import EXTRACTION_PROMPT_VERSION, build_prompt
from app.models import ExtractedRequirement, ExtractionRun, Requirement, SourceDocument
from app.validation_engine import run_validation


class ReplaySourceNotFoundError(ExtractionError):
    pass


class ReplaySourceNotLiveError(ExtractionError):
    pass


def run_extraction(
    session: Session,
    client: ExtractionClient,
    raw_text: str,
    title: str | None = None,
) -> ExtractionRun:
    source_document = SourceDocument(title=title, raw_text=raw_text)
    session.add(source_document)
    session.commit()

    try:
        prompt = build_prompt(raw_text)
        call_result = client.complete(prompt)
        candidates = parse_response(call_result.text)

        resolved: list[tuple] = []
        for candidate in candidates:
            start = raw_text.find(candidate.source_quote)
            if start == -1:
                raise SourceQuoteNotFoundError(
                    "source_quote could not be located verbatim in the "
                    f"source text: {candidate.source_quote!r}"
                )
            end = start + len(candidate.source_quote)
            resolved.append((candidate, start, end))

        extraction_run = ExtractionRun(
            source_document_id=source_document.id,
            model_name=client.model_name,
            prompt_version=EXTRACTION_PROMPT_VERSION,
            mode="live",
            raw_response=call_result.raw_response,
        )
        session.add(extraction_run)
        session.flush()

        for candidate, start, end in resolved:
            extracted = ExtractedRequirement(
                extraction_run_id=extraction_run.id,
                requirement_text=candidate.requirement_text,
                source_span_start=start,
                source_span_end=end,
                source_quote=candidate.source_quote,
            )
            session.add(extracted)
            session.flush()

            session.add(
                Requirement(
                    source_extraction_id=extracted.id,
                    current_text=candidate.requirement_text,
                    origin="ai_generated",
                )
            )

        session.commit()
    except Exception:
        session.rollback()
        raise

    session.refresh(extraction_run)
    return extraction_run


def run_replay(session: Session, live_extraction_run_id: int) -> ExtractionRun:
    live_run = session.get(ExtractionRun, live_extraction_run_id)
    if live_run is None:
        raise ReplaySourceNotFoundError(
            f"Extraction run {live_extraction_run_id} does not exist."
        )
    if live_run.mode != "live":
        raise ReplaySourceNotLiveError(
            "Only a live extraction run can be replayed - extraction run "
            f"{live_extraction_run_id} has mode={live_run.mode!r}."
        )

    try:
        replay_run = ExtractionRun(
            source_document_id=live_run.source_document_id,
            model_name=live_run.model_name,
            prompt_version=live_run.prompt_version,
            mode="replay",
            replayed_from_run_id=live_run.id,
        )
        session.add(replay_run)
        session.flush()

        originals = (
            session.execute(
                select(ExtractedRequirement).where(
                    ExtractedRequirement.extraction_run_id == live_run.id
                )
            )
            .scalars()
            .all()
        )

        new_requirement_ids: list[int] = []
        for original in originals:
            copied = ExtractedRequirement(
                extraction_run_id=replay_run.id,
                requirement_text=original.requirement_text,
                source_span_start=original.source_span_start,
                source_span_end=original.source_span_end,
                source_quote=original.source_quote,
            )
            session.add(copied)
            session.flush()

            requirement = Requirement(
                source_extraction_id=copied.id,
                current_text=copied.requirement_text,
                origin="ai_generated",
            )
            session.add(requirement)
            session.flush()
            new_requirement_ids.append(requirement.id)

        session.commit()
    except Exception:
        session.rollback()
        raise

    # Validation is a separate, independently atomic step per requirement -
    # run_validation() owns its own commit/rollback boundary, exactly as it
    # does for every other caller. This mirrors how live extraction is
    # followed by a separate validate step (see app/ui/streamlit_app.py),
    # rather than folding validation into the extraction-copy transaction.
    for requirement_id in new_requirement_ids:
        run_validation(session, requirement_id)

    session.refresh(replay_run)
    return replay_run
