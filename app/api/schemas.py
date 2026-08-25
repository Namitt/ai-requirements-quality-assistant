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
    requirement_id: int | None = None
    acceptance_criterion_id: int | None = None
    validator_version: str
    run_at: datetime
    results: list[ValidationResultOut]


class ValidationTriggerResponse(BaseModel):
    requirement: RequirementOut
    validation_run: ValidationRunOut


class RequirementPatchRequest(BaseModel):
    current_text: str = Field(
        min_length=1, description="The analyst's edited requirement text."
    )


class ApproveRequest(BaseModel):
    acknowledge_warning: bool = Field(
        default=False,
        description=(
            "Must be explicitly true to approve a requirement whose latest "
            "validation_state is 'warn'. Never inferred from calling this "
            "endpoint."
        ),
    )


class RequirementEditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    previous_text: str
    new_text: str
    edited_by: str | None
    edited_at: datetime


class ExtractedEvidenceOut(BaseModel):
    id: int
    requirement_text: str
    source_quote: str
    source_span_start: int
    source_span_end: int
    source_document_id: int


class RequirementReviewResponse(BaseModel):
    requirement: RequirementOut
    extracted_evidence: ExtractedEvidenceOut | None
    latest_validation: ValidationRunOut | None
    edit_history: list[RequirementEditOut]


class RequirementSummaryOut(BaseModel):
    id: int
    current_text: str
    source_document_id: int | None
    source_document_title: str | None
    origin: str
    model_name: str | None
    mode: str | None
    validation_state: str
    review_status: str
    warn_acknowledged: bool
    acceptance_criteria_count: int


class AcceptanceCriteriaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_extraction_id: int
    current_text: str
    validation_state: str
    review_status: str
    warn_acknowledged_at: datetime | None
    warn_acknowledged_by: str | None
    created_at: datetime
    updated_at: datetime


class ExtractedAcceptanceCriterionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    requirement_id: int
    criterion_text: str
    mode: str
    replayed_from_id: int | None
    model_name: str
    prompt_version: str
    created_at: datetime
    acceptance_criteria: list[AcceptanceCriteriaOut] = Field(default_factory=list)


class AcceptanceCriteriaPatchRequest(BaseModel):
    current_text: str = Field(
        min_length=1, description="The analyst's edited acceptance criterion text."
    )


class AcceptanceCriteriaApproveRequest(BaseModel):
    acknowledge_warning: bool = Field(
        default=False,
        description=(
            "Must be explicitly true to approve an acceptance criterion whose "
            "latest validation_state is 'warn'. Never inferred from calling "
            "this endpoint."
        ),
    )


class AcceptanceCriterionEditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    previous_text: str
    new_text: str
    edited_by: str | None
    edited_at: datetime


class AcceptanceCriterionProvenanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    requirement_id: int
    criterion_text: str
    mode: str
    replayed_from_id: int | None
    model_name: str
    prompt_version: str
    created_at: datetime


class AcceptanceCriteriaValidationTriggerResponse(BaseModel):
    acceptance_criterion: AcceptanceCriteriaOut
    validation_run: ValidationRunOut


class AcceptanceCriteriaReviewResponse(BaseModel):
    acceptance_criterion: AcceptanceCriteriaOut
    provenance: AcceptanceCriterionProvenanceOut
    parent_requirement: RequirementOut
    extracted_evidence: ExtractedEvidenceOut | None
    latest_validation: ValidationRunOut | None
    edit_history: list[AcceptanceCriterionEditOut]
