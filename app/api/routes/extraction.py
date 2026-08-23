from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db_session, get_extraction_client
from app.api.schemas import ExtractedRequirementOut, ExtractionRequest, ExtractionRunOut, SourceDocumentOut
from app.extraction.client import ExtractionClient
from app.extraction_engine import run_extraction, run_replay
from app.models import ExtractedRequirement, ExtractionRun, SourceDocument

router = APIRouter(tags=["extraction"])


def _extraction_run_query():
    return select(ExtractionRun).options(
        selectinload(ExtractionRun.extracted_requirements).selectinload(
            ExtractedRequirement.requirements
        )
    )


@router.post(
    "/extractions",
    response_model=ExtractionRunOut,
    status_code=status.HTTP_201_CREATED,
    summary="Submit source text and run live AI extraction",
)
def create_extraction(
    payload: ExtractionRequest,
    session: Session = Depends(get_db_session),
    client: ExtractionClient = Depends(get_extraction_client),
) -> ExtractionRun:
    created = run_extraction(session, client, payload.raw_text, payload.title)

    stmt = _extraction_run_query().where(ExtractionRun.id == created.id)
    return session.execute(stmt).scalar_one()


@router.get(
    "/extraction-runs",
    response_model=list[ExtractionRunOut],
    summary="List all extraction runs (live and replay)",
)
def list_extraction_runs(session: Session = Depends(get_db_session)) -> list[ExtractionRun]:
    stmt = _extraction_run_query().order_by(ExtractionRun.id)
    return session.execute(stmt).scalars().all()


@router.post(
    "/extraction-runs/{extraction_run_id}/replay",
    response_model=ExtractionRunOut,
    status_code=status.HTTP_201_CREATED,
    summary="Replay a previous live extraction run without a live AI call",
)
def replay_extraction_run(
    extraction_run_id: int, session: Session = Depends(get_db_session)
) -> ExtractionRun:
    created = run_replay(session, extraction_run_id)

    stmt = _extraction_run_query().where(ExtractionRun.id == created.id)
    return session.execute(stmt).scalar_one()


@router.get(
    "/source-documents/{source_document_id}",
    response_model=SourceDocumentOut,
    summary="Retrieve a submitted source document",
)
def get_source_document(
    source_document_id: int, session: Session = Depends(get_db_session)
) -> SourceDocument:
    document = session.get(SourceDocument, source_document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Source document not found.")
    return document


@router.get(
    "/extraction-runs/{extraction_run_id}",
    response_model=ExtractionRunOut,
    summary="Retrieve an extraction run and its extracted requirements",
)
def get_extraction_run(
    extraction_run_id: int, session: Session = Depends(get_db_session)
) -> ExtractionRun:
    stmt = _extraction_run_query().where(ExtractionRun.id == extraction_run_id)
    run = session.execute(stmt).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Extraction run not found.")
    return run


@router.get(
    "/extracted-requirements/{extracted_requirement_id}",
    response_model=ExtractedRequirementOut,
    summary="Retrieve a single extracted (immutable, AI-original) requirement candidate",
)
def get_extracted_requirement(
    extracted_requirement_id: int, session: Session = Depends(get_db_session)
) -> ExtractedRequirement:
    stmt = (
        select(ExtractedRequirement)
        .options(selectinload(ExtractedRequirement.requirements))
        .where(ExtractedRequirement.id == extracted_requirement_id)
    )
    extracted = session.execute(stmt).scalar_one_or_none()
    if extracted is None:
        raise HTTPException(status_code=404, detail="Extracted requirement not found.")
    return extracted
