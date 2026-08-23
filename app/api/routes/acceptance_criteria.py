from __future__ import annotations

import getpass
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.acceptance_criteria_engine import draft_acceptance_criteria, replay_acceptance_criteria
from app.acceptance_criteria_validation_engine import run_acceptance_criteria_validation
from app.api.deps import get_db_session, get_extraction_client
from app.api.schemas import (
    AcceptanceCriteriaApproveRequest,
    AcceptanceCriteriaOut,
    AcceptanceCriteriaPatchRequest,
    AcceptanceCriteriaReviewResponse,
    AcceptanceCriteriaValidationTriggerResponse,
    AcceptanceCriterionEditOut,
    AcceptanceCriterionProvenanceOut,
    ExtractedAcceptanceCriterionOut,
    ExtractedEvidenceOut,
    RequirementOut,
    ValidationResultOut,
    ValidationRunOut,
)
from app.extraction.client import ExtractionClient
from app.models import (
    AcceptanceCriterion,
    AcceptanceCriterionEdit,
    ExtractedAcceptanceCriterion,
    ExtractedRequirement,
    Requirement,
    ValidationResult,
    ValidationRun,
)

router = APIRouter(tags=["acceptance-criteria"])


def _extracted_ac_query():
    return select(ExtractedAcceptanceCriterion).options(
        selectinload(ExtractedAcceptanceCriterion.acceptance_criteria)
    )


def _latest_ac_validation_run(session: Session, acceptance_criterion_id: int) -> ValidationRun | None:
    stmt = (
        select(ValidationRun)
        .where(ValidationRun.acceptance_criterion_id == acceptance_criterion_id)
        .options(selectinload(ValidationRun.results).selectinload(ValidationResult.rule))
        .order_by(ValidationRun.id.desc())
        .limit(1)
    )
    return session.execute(stmt).scalars().first()


def _to_validation_run_out(validation_run: ValidationRun) -> ValidationRunOut:
    return ValidationRunOut(
        id=validation_run.id,
        requirement_id=validation_run.requirement_id,
        acceptance_criterion_id=validation_run.acceptance_criterion_id,
        validator_version=validation_run.validator_version,
        run_at=validation_run.run_at,
        results=[
            ValidationResultOut(
                rule_code=result.rule.code,
                result=result.result,
                message=result.message,
                recommended_action=result.recommended_action,
            )
            for result in validation_run.results
        ],
    )


@router.post(
    "/requirements/{requirement_id}/acceptance-criteria",
    response_model=AcceptanceCriteriaOut,
    status_code=status.HTTP_201_CREATED,
    summary="Draft an AI-generated acceptance criterion for a requirement",
)
def create_acceptance_criteria(
    requirement_id: int,
    session: Session = Depends(get_db_session),
    client: ExtractionClient = Depends(get_extraction_client),
) -> AcceptanceCriterion:
    requirement = session.get(Requirement, requirement_id)
    if requirement is None:
        raise HTTPException(status_code=404, detail="Requirement not found.")

    return draft_acceptance_criteria(session, client, requirement_id)


@router.get(
    "/requirements/{requirement_id}/acceptance-criteria",
    response_model=list[AcceptanceCriteriaOut],
    summary="List acceptance criteria drafted for a requirement",
)
def list_acceptance_criteria(
    requirement_id: int, session: Session = Depends(get_db_session)
) -> list[AcceptanceCriterion]:
    requirement = session.get(Requirement, requirement_id)
    if requirement is None:
        raise HTTPException(status_code=404, detail="Requirement not found.")

    stmt = (
        select(AcceptanceCriterion)
        .join(
            ExtractedAcceptanceCriterion,
            AcceptanceCriterion.source_extraction_id == ExtractedAcceptanceCriterion.id,
        )
        .where(ExtractedAcceptanceCriterion.requirement_id == requirement_id)
        .order_by(AcceptanceCriterion.id)
    )
    return session.execute(stmt).scalars().all()


@router.get(
    "/extracted-acceptance-criteria/{extracted_id}",
    response_model=ExtractedAcceptanceCriterionOut,
    summary="Retrieve a single extracted (immutable, AI-original) acceptance criterion",
)
def get_extracted_acceptance_criterion(
    extracted_id: int, session: Session = Depends(get_db_session)
) -> ExtractedAcceptanceCriterion:
    stmt = _extracted_ac_query().where(ExtractedAcceptanceCriterion.id == extracted_id)
    extracted = session.execute(stmt).scalar_one_or_none()
    if extracted is None:
        raise HTTPException(
            status_code=404, detail="Extracted acceptance criterion not found."
        )
    return extracted


@router.post(
    "/extracted-acceptance-criteria/{extracted_id}/replay",
    response_model=ExtractedAcceptanceCriterionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Replay a previous live acceptance-criteria draft without a live AI call",
)
def replay_extracted_acceptance_criterion(
    extracted_id: int, session: Session = Depends(get_db_session)
) -> ExtractedAcceptanceCriterion:
    created = replay_acceptance_criteria(session, extracted_id)

    stmt = _extracted_ac_query().where(
        ExtractedAcceptanceCriterion.id == created.source_extraction_id
    )
    return session.execute(stmt).scalar_one()


@router.post(
    "/acceptance-criteria/{acceptance_criterion_id}/validate",
    response_model=AcceptanceCriteriaValidationTriggerResponse,
    summary="Run deterministic validation for an acceptance criterion",
)
def validate_acceptance_criterion(
    acceptance_criterion_id: int, session: Session = Depends(get_db_session)
) -> AcceptanceCriteriaValidationTriggerResponse:
    criterion = session.get(AcceptanceCriterion, acceptance_criterion_id)
    if criterion is None:
        raise HTTPException(status_code=404, detail="Acceptance criterion not found.")

    updated_criterion = run_acceptance_criteria_validation(session, acceptance_criterion_id)

    latest_run = _latest_ac_validation_run(session, acceptance_criterion_id)
    return AcceptanceCriteriaValidationTriggerResponse(
        acceptance_criterion=AcceptanceCriteriaOut.model_validate(updated_criterion),
        validation_run=_to_validation_run_out(latest_run),
    )


@router.patch(
    "/acceptance-criteria/{acceptance_criterion_id}",
    response_model=AcceptanceCriteriaOut,
    summary="Edit a pending acceptance criterion's text and re-validate it",
)
def patch_acceptance_criterion(
    acceptance_criterion_id: int,
    payload: AcceptanceCriteriaPatchRequest,
    session: Session = Depends(get_db_session),
) -> AcceptanceCriterion:
    criterion = session.get(AcceptanceCriterion, acceptance_criterion_id)
    if criterion is None:
        raise HTTPException(status_code=404, detail="Acceptance criterion not found.")

    if criterion.review_status != "pending":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Acceptance criterion is '{criterion.review_status}' and "
                "cannot be edited. Only pending acceptance criteria can be "
                "edited."
            ),
        )

    session.add(
        AcceptanceCriterionEdit(
            acceptance_criterion_id=criterion.id,
            previous_text=criterion.current_text,
            new_text=payload.current_text,
            edited_by=getpass.getuser(),
        )
    )
    criterion.current_text = payload.current_text

    # Mirrors the requirement PATCH pattern: the edit-history row and the
    # text change above are staged but not yet committed, so they are swept
    # into the same atomic transaction as the new validation run via
    # run_acceptance_criteria_validation()'s own commit/rollback boundary.
    return run_acceptance_criteria_validation(session, acceptance_criterion_id)


@router.post(
    "/acceptance-criteria/{acceptance_criterion_id}/approve",
    response_model=AcceptanceCriteriaOut,
    summary="Approve an acceptance criterion after human review",
)
def approve_acceptance_criterion(
    acceptance_criterion_id: int,
    payload: AcceptanceCriteriaApproveRequest = AcceptanceCriteriaApproveRequest(),
    session: Session = Depends(get_db_session),
) -> AcceptanceCriterion:
    criterion = session.get(AcceptanceCriterion, acceptance_criterion_id)
    if criterion is None:
        raise HTTPException(status_code=404, detail="Acceptance criterion not found.")

    if criterion.review_status != "pending":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Acceptance criterion is '{criterion.review_status}' and "
                "cannot be approved. Only pending acceptance criteria can be "
                "approved."
            ),
        )

    if criterion.validation_state == "not_validated":
        raise HTTPException(
            status_code=409,
            detail=(
                "Acceptance criterion has not been validated yet and cannot "
                "be approved."
            ),
        )

    if criterion.validation_state == "fail":
        raise HTTPException(
            status_code=409,
            detail=(
                "Acceptance criterion has a FAIL validation result and "
                "cannot be approved."
            ),
        )

    if criterion.validation_state == "warn":
        if not payload.acknowledge_warning:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Acceptance criterion has a WARN validation result; "
                    "approval requires acknowledge_warning=true."
                ),
            )
        criterion.warn_acknowledged_at = datetime.now(timezone.utc)
        criterion.warn_acknowledged_by = getpass.getuser()

    criterion.review_status = "approved"
    session.commit()
    session.refresh(criterion)
    return criterion


@router.post(
    "/acceptance-criteria/{acceptance_criterion_id}/reject",
    response_model=AcceptanceCriteriaOut,
    summary="Reject an acceptance criterion after human review",
)
def reject_acceptance_criterion(
    acceptance_criterion_id: int, session: Session = Depends(get_db_session)
) -> AcceptanceCriterion:
    criterion = session.get(AcceptanceCriterion, acceptance_criterion_id)
    if criterion is None:
        raise HTTPException(status_code=404, detail="Acceptance criterion not found.")

    if criterion.review_status != "pending":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Acceptance criterion is '{criterion.review_status}' and "
                "cannot be rejected. Only pending acceptance criteria can be "
                "rejected."
            ),
        )

    criterion.review_status = "rejected"
    session.commit()
    session.refresh(criterion)
    return criterion


@router.get(
    "/acceptance-criteria/{acceptance_criterion_id}/review",
    response_model=AcceptanceCriteriaReviewResponse,
    summary="Retrieve everything needed for a human review screen for an acceptance criterion",
)
def get_acceptance_criterion_review(
    acceptance_criterion_id: int, session: Session = Depends(get_db_session)
) -> AcceptanceCriteriaReviewResponse:
    stmt = (
        select(AcceptanceCriterion)
        .where(AcceptanceCriterion.id == acceptance_criterion_id)
        .options(
            selectinload(AcceptanceCriterion.source_extraction)
            .selectinload(ExtractedAcceptanceCriterion.requirement)
            .selectinload(Requirement.source_extraction)
            .selectinload(ExtractedRequirement.extraction_run),
            selectinload(AcceptanceCriterion.edits),
        )
    )
    criterion = session.execute(stmt).scalar_one_or_none()
    if criterion is None:
        raise HTTPException(status_code=404, detail="Acceptance criterion not found.")

    extracted_ac = criterion.source_extraction
    parent_requirement = extracted_ac.requirement

    extracted_evidence = None
    if parent_requirement.source_extraction is not None:
        extracted = parent_requirement.source_extraction
        extracted_evidence = ExtractedEvidenceOut(
            id=extracted.id,
            requirement_text=extracted.requirement_text,
            source_quote=extracted.source_quote,
            source_span_start=extracted.source_span_start,
            source_span_end=extracted.source_span_end,
            source_document_id=extracted.extraction_run.source_document_id,
        )

    latest_run = _latest_ac_validation_run(session, acceptance_criterion_id)
    latest_validation = _to_validation_run_out(latest_run) if latest_run is not None else None

    edit_history = [
        AcceptanceCriterionEditOut.model_validate(edit)
        for edit in sorted(criterion.edits, key=lambda e: e.edited_at)
    ]

    return AcceptanceCriteriaReviewResponse(
        acceptance_criterion=AcceptanceCriteriaOut.model_validate(criterion),
        provenance=AcceptanceCriterionProvenanceOut.model_validate(extracted_ac),
        parent_requirement=RequirementOut.model_validate(parent_requirement),
        extracted_evidence=extracted_evidence,
        latest_validation=latest_validation,
        edit_history=edit_history,
    )
