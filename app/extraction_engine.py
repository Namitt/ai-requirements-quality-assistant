from __future__ import annotations

from sqlalchemy.orm import Session

from app.extraction import SourceQuoteNotFoundError
from app.extraction.client import ExtractionClient
from app.extraction.parser import parse_response
from app.extraction.prompt import EXTRACTION_PROMPT_VERSION, build_prompt
from app.models import ExtractedRequirement, ExtractionRun, Requirement, SourceDocument


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
