from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.acceptance_criteria_validation_engine import EXPECTED_AC_RULE_CODES
from app.api.deps import get_db_session
from app.api.errors import register_exception_handlers
from app.api.routes.acceptance_criteria import router as acceptance_criteria_router
from app.api.routes.extraction import router as extraction_router
from app.api.routes.requirements import router as requirements_router
from app.models import ValidationRule
from app.validation_engine import EXPECTED_RULE_CODES

_EXPECTED_VALIDATION_RULE_CODES = set(EXPECTED_RULE_CODES) | set(EXPECTED_AC_RULE_CODES)

app = FastAPI(
    title="AI Requirements Quality Assistant API",
    description=(
        "Exposes AI-assisted requirement extraction and deterministic "
        "validation. AI performs extraction only; the deterministic "
        "validation engine remains the sole authority on requirement "
        "quality."
    ),
    version="0.1.0",
)

register_exception_handlers(app)

app.include_router(extraction_router)
app.include_router(requirements_router)
app.include_router(acceptance_criteria_router)


@app.get("/health", summary="Health check", tags=["health"])
def health_check(session: Session = Depends(get_db_session)) -> dict:
    # A 200 here is meant to mean "this service can actually do its job" -
    # not just "the process is running." That requires the database to be
    # reachable and migrated, and the validation_rules catalog to be fully
    # seeded, since every validate call depends on it (see the fresh-database
    # seeding gap this check exists to surface).
    try:
        seeded_codes = {
            code for (code,) in session.execute(select(ValidationRule.code)).all()
        }
    except OperationalError as exc:
        raise HTTPException(
            status_code=503,
            detail="Database is unreachable or not migrated. Run `alembic upgrade head`.",
        ) from exc

    missing_codes = _EXPECTED_VALIDATION_RULE_CODES - seeded_codes
    if missing_codes:
        raise HTTPException(
            status_code=503,
            detail=(
                "Database is reachable but the validation_rules catalog is "
                f"incomplete (missing: {', '.join(sorted(missing_codes))}). "
                "Run `alembic upgrade head`."
            ),
        )

    return {"status": "ok"}
