from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ExtractionRequest(BaseModel):
    raw_text: str = Field(
        min_length=1,
        description="Unstructured source text to extract candidate requirements from.",
    )
    title: str | None = Field(
        default=None, description="Optional label for the source document."
    )


class RequirementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_extraction_id: int | None
    current_text: str
    origin: str
    validation_state: str
    review_status: str
    warn_acknowledged_at: datetime | None
    warn_acknowledged_by: str | None
    created_at: datetime
    updated_at: datetime


class ExtractedRequirementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    extraction_run_id: int
    requirement_text: str
    source_span_start: int
    source_span_end: int
    source_quote: str
    created_at: datetime
    requirements: list[RequirementOut] = Field(default_factory=list)


class ExtractionRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_document_id: int
    model_name: str
    prompt_version: str
    mode: str
    replayed_from_run_id: int | None
    run_at: datetime
    extracted_requirements: list[ExtractedRequirementOut] = Field(default_factory=list)


class SourceDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str | None
    raw_text: str
    created_at: datetime


class ValidationResultOut(BaseModel):
    rule_code: str
    result: str
    message: str
    recommended_action: str | None


class ValidationRunOut(BaseModel):
    id: int
    requirement_id: int
    validator_version: str
    run_at: datetime
    results: list[ValidationResultOut]


class ValidationTriggerResponse(BaseModel):
    requirement: RequirementOut
    validation_run: ValidationRunOut
