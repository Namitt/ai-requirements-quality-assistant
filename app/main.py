from __future__ import annotations

from fastapi import FastAPI

from app.api.errors import register_exception_handlers
from app.api.routes.extraction import router as extraction_router
from app.api.routes.requirements import router as requirements_router

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


@app.get("/health", summary="Health check", tags=["health"])
def health_check() -> dict:
    return {"status": "ok"}
