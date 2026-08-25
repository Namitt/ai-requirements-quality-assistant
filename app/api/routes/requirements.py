from __future__ import annotations

import getpass
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db_session
from app.api.schemas import (
    ApproveRequest,
    ExtractedEvidenceOut,
    RequirementEditOut,
    RequirementOut,
    RequirementPatchRequest,
    RequirementReviewResponse,
    RequirementSummaryOut,
    ValidationResultOut,
    ValidationRunOut,
    ValidationTriggerResponse,
)
from app.models import (
    ExtractedAcceptanceCriterion,
    ExtractedRequirement,
    ExtractionRun,
    Requirement,
    RequirementEdit,
    ValidationResult,
    ValidationRun,
)
from app.validation_engine import run_validation

router = APIRouter(tags=["requirements"])


@router.get(
    "/requirements", response_model=list[RequirementOut], summary="List all requirements"
)
def list_requirements(session: Session = Depends(get_db_session)) -> list[Requirement]:
    return session.execute(select(Requirement).order_by(Requirement.id)).scalars().all()


@router.get(
    "/requirements/summary",
    response_model=list[RequirementSummaryOut],
    summary="Retrieve a requirement-level audit/traceability projection across all requirements",
)
def get_requirements_summary(
    session: Session = Depends(get_db_session),
) -> list[RequirementSummaryOut]:
    # Declared before /requirements/{requirement_id}: that route's path
    # parameter is untyped in the path template (only Python-typed), so
    # Starlette's routing would otherwise match "summary" as a requirement_id
    # string and fail int coercion with a 422 instead of ever reaching this
    # route. Registration order is what avoids that, not the path text.
    stmt = (
        select(Requirement)
        .options(
            selectinload(Requirement.source_extraction)
            .selectinload(ExtractedRequirement.extraction_run)
            .selectinload(ExtractionRun.source_document),
            selectinload(Requirement.extracted_acceptance_criteria).selectinload(
                ExtractedAcceptanceCriterion.acceptance_criteria
            ),
        )
        .order_by(Requirement.id)
    )
    requirements = session.execute(stmt).scalars().all()

    rows: list[RequirementSummaryOut] = []
    for requirement in requirements:
        extracted = requirement.source_extraction
        extraction_run = extracted.extraction_run if extracted is not None else None
        source_document = (
            extraction_run.source_document if extraction_run is not None else None
        )
        acceptance_criteria_count = sum(
            len(extracted_ac.acceptance_criteria)
            for extracted_ac in requirement.extracted_acceptance_criteria
        )

        rows.append(
            RequirementSummaryOut(
                id=requirement.id,
                current_text=requirement.current_text,
                source_document_id=source_document.id if source_document else None,
                source_document_title=(
                    source_document.title if source_document else None
                ),
                origin=requirement.origin,
                model_name=extraction_run.model_name if extraction_run else None,
                mode=extraction_run.mode if extraction_run else None,
                validation_state=requirement.validation_state,
                review_status=requirement.review_status,
                warn_acknowledged=requirement.warn_acknowledged_at is not None,
                acceptance_criteria_count=acceptance_criteria_count,
            )
        )

    return rows


@router.get(
    "/requirements/{requirement_id}",
    response_model=RequirementOut,
    summary="Retrieve a single requirement",
)
def get_requirement(
    requirement_id: int, session: Session = Depends(get_db_session)
) -> Requirement:
    requirement = session.get(Requirement, requirement_id)
    if requirement is None:
        raise HTTPException(status_code=404, detail="Requirement not found.")
    return requirement


def _latest_validation_run(session: Session, requirement_id: int) -> ValidationRun | None:
    stmt = (
        select(ValidationRun)
        .where(ValidationRun.requirement_id == requirement_id)
        .options(selectinload(ValidationRun.results).selectinload(ValidationResult.rule))
        .order_by(ValidationRun.id.desc())
        .limit(1)
    )
    return session.execute(stmt).scalars().first()


def _to_validation_run_out(validation_run: ValidationRun) -> ValidationRunOut:
    return ValidationRunOut(
        id=validation_run.id,
        requirement_id=validation_run.requirement_id,
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
    "/requirements/{requirement_id}/validate",
    response_model=ValidationTriggerResponse,
    summary="Run deterministic validation for a requirement",
)
def validate_requirement(
    requirement_id: int, session: Session = Depends(get_db_session)
) -> ValidationTriggerResponse:
    requirement = session.get(Requirement, requirement_id)
    if requirement is None:
        raise HTTPException(status_code=404, detail="Requirement not found.")

    if requirement.review_status != "pending":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Requirement is '{requirement.review_status}' and cannot be "
                "re-validated. Only pending requirements can be validated."
            ),
        )

    updated_requirement = run_validation(session, requirement_id)

    latest_run = _latest_validation_run(session, requirement_id)
    return ValidationTriggerResponse(
        requirement=RequirementOut.model_validate(updated_requirement),
        validation_run=_to_validation_run_out(latest_run),
    )


@router.get(
    "/requirements/{requirement_id}/validation-results",
    response_model=ValidationRunOut,
    summary="Retrieve the latest validation results for a requirement",
)
def get_validation_results(
    requirement_id: int, session: Session = Depends(get_db_session)
) -> ValidationRunOut:
    requirement = session.get(Requirement, requirement_id)
    if requirement is None:
        raise HTTPException(status_code=404, detail="Requirement not found.")

    latest_run = _latest_validation_run(session, requirement_id)
    if latest_run is None:
        raise HTTPException(
            status_code=404, detail="No validation has been run for this requirement yet."
        )
    return _to_validation_run_out(latest_run)


# ---------------------------------------------------------------------------
# human review workflow: edit, approve, reject, composite review
# ---------------------------------------------------------------------------


@router.patch(
    "/requirements/{requirement_id}",
    response_model=RequirementOut,
    summary="Edit a pending requirement's text and re-validate it",
)
def patch_requirement(
    requirement_id: int,
    payload: RequirementPatchRequest,
    session: Session = Depends(get_db_session),
) -> Requirement:
    requirement = session.get(Requirement, requirement_id)
    if requirement is None:
        raise HTTPException(status_code=404, detail="Requirement not found.")

    if requirement.review_status != "pending":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Requirement is '{requirement.review_status}' and cannot be "
                "edited. Only pending requirements can be edited."
            ),
        )

    session.add(
        RequirementEdit(
            requirement_id=requirement.id,
            previous_text=requirement.current_text,
            new_text=payload.current_text,
            edited_by=getpass.getuser(),
        )
    )
    requirement.current_text = payload.current_text

    # run_validation() owns its own commit/rollback boundary on this same
    # session. The edit-history row and the current_text change above are
    # staged but not yet committed, so they are swept into the exact same
    # atomic transaction as the new validation run: both succeed together
    # on run_validation()'s commit, or both are undone together on its
    # rollback if a rule raises. No partial edit can be left behind.
    return run_validation(session, requirement_id)


@router.post(
    "/requirements/{requirement_id}/approve",
    response_model=RequirementOut,
    summary="Approve a requirement after human review",
)
def approve_requirement(
    requirement_id: int,
    payload: ApproveRequest = ApproveRequest(),
    session: Session = Depends(get_db_session),
) -> Requirement:
    requirement = session.get(Requirement, requirement_id)
    if requirement is None:
        raise HTTPException(status_code=404, detail="Requirement not found.")

    if requirement.review_status != "pending":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Requirement is '{requirement.review_status}' and cannot be "
                "approved. Only pending requirements can be approved."
            ),
        )

    if requirement.validation_state == "not_validated":
        raise HTTPException(
            status_code=409,
            detail="Requirement has not been validated yet and cannot be approved.",
        )

    if requirement.validation_state == "fail":
        raise HTTPException(
            status_code=409,
            detail="Requirement has a FAIL validation result and cannot be approved.",
        )

    if requirement.validation_state == "warn":
        if not payload.acknowledge_warning:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Requirement has a WARN validation result; approval "
                    "requires acknowledge_warning=true."
                ),
            )
        # Acknowledgement is recorded explicitly here, only because the
        # analyst set acknowledge_warning=true - never inferred merely from
        # this endpoint being called.
        requirement.warn_acknowledged_at = datetime.now(timezone.utc)
        requirement.warn_acknowledged_by = getpass.getuser()

    requirement.review_status = "approved"
    session.commit()
    session.refresh(requirement)
    return requirement


@router.post(
    "/requirements/{requirement_id}/reject",
    response_model=RequirementOut,
    summary="Reject a requirement after human review",
)
def reject_requirement(
    requirement_id: int, session: Session = Depends(get_db_session)
) -> Requirement:
    requirement = session.get(Requirement, requirement_id)
    if requirement is None:
        raise HTTPException(status_code=404, detail="Requirement not found.")

    if requirement.review_status != "pending":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Requirement is '{requirement.review_status}' and cannot be "
                "rejected. Only pending requirements can be rejected."
            ),
        )

    requirement.review_status = "rejected"
    session.commit()
    session.refresh(requirement)
    return requirement


@router.get(
    "/requirements/{requirement_id}/review",
    response_model=RequirementReviewResponse,
    summary="Retrieve everything needed for a human review screen",
)
def get_requirement_review(
    requirement_id: int, session: Session = Depends(get_db_session)
) -> RequirementReviewResponse:
    stmt = (
        select(Requirement)
        .where(Requirement.id == requirement_id)
        .options(
            selectinload(Requirement.source_extraction).selectinload(
                ExtractedRequirement.extraction_run
            ),
            selectinload(Requirement.edits),
        )
    )
    requirement = session.execute(stmt).scalar_one_or_none()
    if requirement is None:
        raise HTTPException(status_code=404, detail="Requirement not found.")

    extracted_evidence = None
    if requirement.source_extraction is not None:
        extracted = requirement.source_extraction
        extracted_evidence = ExtractedEvidenceOut(
            id=extracted.id,
            requirement_text=extracted.requirement_text,
            source_quote=extracted.source_quote,
            source_span_start=extracted.source_span_start,
            source_span_end=extracted.source_span_end,
            source_document_id=extracted.extraction_run.source_document_id,
        )

    latest_run = _latest_validation_run(session, requirement_id)
    latest_validation = _to_validation_run_out(latest_run) if latest_run is not None else None

    edit_history = [
        RequirementEditOut.model_validate(edit)
        for edit in sorted(requirement.edits, key=lambda e: e.edited_at)
    ]

    return RequirementReviewResponse(
        requirement=RequirementOut.model_validate(requirement),
        extracted_evidence=extracted_evidence,
        latest_validation=latest_validation,
        edit_history=edit_history,
    )
