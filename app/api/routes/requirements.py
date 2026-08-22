from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db_session
from app.api.schemas import (
    RequirementOut,
    ValidationResultOut,
    ValidationRunOut,
    ValidationTriggerResponse,
)
from app.models import Requirement, ValidationResult, ValidationRun
from app.validation_engine import run_validation

router = APIRouter(tags=["requirements"])


@router.get(
    "/requirements", response_model=list[RequirementOut], summary="List all requirements"
)
def list_requirements(session: Session = Depends(get_db_session)) -> list[Requirement]:
    return session.execute(select(Requirement).order_by(Requirement.id)).scalars().all()


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
