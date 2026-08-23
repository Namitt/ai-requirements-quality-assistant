from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


# Timestamps are generated here as UTC. SQLite has no native timezone-aware
# storage, so SQLAlchemy's DateTime type persists these values without
# offset information and returns naive datetimes on read. The naive stored
# values are UTC by convention — every write to a timestamp column must go
# through this function (or an equivalent UTC source) to keep that true.
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SourceDocument(Base):
    __tablename__ = "source_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)

    extraction_runs: Mapped[list["ExtractionRun"]] = relationship(
        back_populates="source_document"
    )


class ExtractionRun(Base):
    __tablename__ = "extraction_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_document_id: Mapped[int] = mapped_column(
        ForeignKey("source_documents.id", ondelete="RESTRICT"), nullable=False
    )
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    replayed_from_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("extraction_runs.id", ondelete="RESTRICT"), nullable=True
    )
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)

    source_document: Mapped["SourceDocument"] = relationship(
        back_populates="extraction_runs"
    )
    extracted_requirements: Mapped[list["ExtractedRequirement"]] = relationship(
        back_populates="extraction_run"
    )

    __table_args__ = (
        CheckConstraint("mode IN ('live','replay')", name="ck_extraction_runs_mode"),
        CheckConstraint(
            "(mode = 'live' AND replayed_from_run_id IS NULL) "
            "OR (mode = 'replay' AND replayed_from_run_id IS NOT NULL)",
            name="ck_extraction_runs_replay_pairing",
        ),
    )


class ExtractedRequirement(Base):
    __tablename__ = "extracted_requirements"

    id: Mapped[int] = mapped_column(primary_key=True)
    extraction_run_id: Mapped[int] = mapped_column(
        ForeignKey("extraction_runs.id", ondelete="RESTRICT"), nullable=False
    )
    requirement_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_span_start: Mapped[int] = mapped_column(nullable=False)
    source_span_end: Mapped[int] = mapped_column(nullable=False)
    source_quote: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)

    extraction_run: Mapped["ExtractionRun"] = relationship(
        back_populates="extracted_requirements"
    )
    requirements: Mapped[list["Requirement"]] = relationship(
        back_populates="source_extraction"
    )


class Requirement(Base):
    __tablename__ = "requirements"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_extraction_id: Mapped[int | None] = mapped_column(
        ForeignKey("extracted_requirements.id", ondelete="RESTRICT"), nullable=True
    )
    current_text: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[str] = mapped_column(Text, nullable=False)
    validation_state: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'not_validated'")
    )
    review_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pending'")
    )
    warn_acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    warn_acknowledged_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )

    source_extraction: Mapped["ExtractedRequirement | None"] = relationship(
        back_populates="requirements"
    )
    edits: Mapped[list["RequirementEdit"]] = relationship(back_populates="requirement")
    validation_runs: Mapped[list["ValidationRun"]] = relationship(
        back_populates="requirement"
    )
    extracted_acceptance_criteria: Mapped[list["ExtractedAcceptanceCriterion"]] = relationship(
        back_populates="requirement"
    )

    __table_args__ = (
        CheckConstraint(
            "origin IN ('ai_generated','manual')", name="ck_requirements_origin"
        ),
        CheckConstraint(
            "validation_state IN ('not_validated','pass','warn','fail')",
            name="ck_requirements_validation_state",
        ),
        CheckConstraint(
            "review_status IN ('pending','approved','rejected')",
            name="ck_requirements_review_status",
        ),
        CheckConstraint(
            "review_status != 'approved' OR validation_state != 'fail'",
            name="ck_requirements_fail_blocks_approval",
        ),
        CheckConstraint(
            "review_status != 'approved' OR validation_state != 'not_validated'",
            name="ck_requirements_not_validated_blocks_approval",
        ),
        CheckConstraint(
            "review_status != 'approved' OR validation_state != 'warn' "
            "OR warn_acknowledged_at IS NOT NULL",
            name="ck_requirements_warn_requires_ack",
        ),
    )


class RequirementEdit(Base):
    __tablename__ = "requirement_edits"

    id: Mapped[int] = mapped_column(primary_key=True)
    requirement_id: Mapped[int] = mapped_column(
        ForeignKey("requirements.id", ondelete="RESTRICT"), nullable=False
    )
    previous_text: Mapped[str] = mapped_column(Text, nullable=False)
    new_text: Mapped[str] = mapped_column(Text, nullable=False)
    edited_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    edited_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)

    requirement: Mapped["Requirement"] = relationship(back_populates="edits")


class ValidationRule(Base):
    __tablename__ = "validation_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    default_severity: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("code", name="uq_validation_rules_code"),
        CheckConstraint(
            "default_severity IN ('warn','fail')",
            name="ck_validation_rules_default_severity",
        ),
    )


class ValidationRun(Base):
    __tablename__ = "validation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    requirement_id: Mapped[int | None] = mapped_column(
        ForeignKey("requirements.id", ondelete="RESTRICT"), nullable=True
    )
    acceptance_criterion_id: Mapped[int | None] = mapped_column(
        ForeignKey("acceptance_criteria.id", ondelete="RESTRICT"), nullable=True
    )
    validator_version: Mapped[str] = mapped_column(Text, nullable=False)
    run_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)

    requirement: Mapped["Requirement | None"] = relationship(
        back_populates="validation_runs"
    )
    acceptance_criterion: Mapped["AcceptanceCriterion | None"] = relationship(
        back_populates="validation_runs"
    )
    results: Mapped[list["ValidationResult"]] = relationship(
        back_populates="validation_run"
    )

    __table_args__ = (
        CheckConstraint(
            "(requirement_id IS NOT NULL AND acceptance_criterion_id IS NULL) "
            "OR (requirement_id IS NULL AND acceptance_criterion_id IS NOT NULL)",
            name="ck_validation_runs_exactly_one_parent",
        ),
    )


class ValidationResult(Base):
    __tablename__ = "validation_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    validation_run_id: Mapped[int] = mapped_column(
        ForeignKey("validation_runs.id", ondelete="RESTRICT"), nullable=False
    )
    rule_id: Mapped[int] = mapped_column(
        ForeignKey("validation_rules.id", ondelete="RESTRICT"), nullable=False
    )
    result: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)

    validation_run: Mapped["ValidationRun"] = relationship(back_populates="results")
    rule: Mapped["ValidationRule"] = relationship()

    __table_args__ = (
        CheckConstraint(
            "result IN ('pass','warn','fail')", name="ck_validation_results_result"
        ),
        UniqueConstraint(
            "validation_run_id", "rule_id", name="uq_validation_results_run_rule"
        ),
    )


class ExtractedAcceptanceCriterion(Base):
    __tablename__ = "extracted_acceptance_criteria"

    id: Mapped[int] = mapped_column(primary_key=True)
    requirement_id: Mapped[int] = mapped_column(
        ForeignKey("requirements.id", ondelete="RESTRICT"), nullable=False
    )
    criterion_text: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    replayed_from_id: Mapped[int | None] = mapped_column(
        ForeignKey("extracted_acceptance_criteria.id", ondelete="RESTRICT"), nullable=True
    )
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)

    requirement: Mapped["Requirement"] = relationship(
        back_populates="extracted_acceptance_criteria"
    )
    acceptance_criteria: Mapped[list["AcceptanceCriterion"]] = relationship(
        back_populates="source_extraction"
    )

    __table_args__ = (
        CheckConstraint(
            "mode IN ('live','replay')", name="ck_extracted_acceptance_criteria_mode"
        ),
        CheckConstraint(
            "(mode = 'live' AND replayed_from_id IS NULL) "
            "OR (mode = 'replay' AND replayed_from_id IS NOT NULL)",
            name="ck_extracted_acceptance_criteria_replay_pairing",
        ),
    )


class AcceptanceCriterion(Base):
    __tablename__ = "acceptance_criteria"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_extraction_id: Mapped[int] = mapped_column(
        ForeignKey("extracted_acceptance_criteria.id", ondelete="RESTRICT"), nullable=False
    )
    current_text: Mapped[str] = mapped_column(Text, nullable=False)
    validation_state: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'not_validated'")
    )
    review_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pending'")
    )
    warn_acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    warn_acknowledged_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )

    source_extraction: Mapped["ExtractedAcceptanceCriterion"] = relationship(
        back_populates="acceptance_criteria"
    )
    edits: Mapped[list["AcceptanceCriterionEdit"]] = relationship(
        back_populates="acceptance_criterion"
    )
    validation_runs: Mapped[list["ValidationRun"]] = relationship(
        back_populates="acceptance_criterion"
    )

    __table_args__ = (
        CheckConstraint(
            "validation_state IN ('not_validated','pass','warn','fail')",
            name="ck_acceptance_criteria_validation_state",
        ),
        CheckConstraint(
            "review_status IN ('pending','approved','rejected')",
            name="ck_acceptance_criteria_review_status",
        ),
        CheckConstraint(
            "review_status != 'approved' OR validation_state != 'fail'",
            name="ck_acceptance_criteria_fail_blocks_approval",
        ),
        CheckConstraint(
            "review_status != 'approved' OR validation_state != 'not_validated'",
            name="ck_acceptance_criteria_not_validated_blocks_approval",
        ),
        CheckConstraint(
            "review_status != 'approved' OR validation_state != 'warn' "
            "OR warn_acknowledged_at IS NOT NULL",
            name="ck_acceptance_criteria_warn_requires_ack",
        ),
    )


class AcceptanceCriterionEdit(Base):
    __tablename__ = "acceptance_criteria_edits"

    id: Mapped[int] = mapped_column(primary_key=True)
    acceptance_criterion_id: Mapped[int] = mapped_column(
        ForeignKey("acceptance_criteria.id", ondelete="RESTRICT"), nullable=False
    )
    previous_text: Mapped[str] = mapped_column(Text, nullable=False)
    new_text: Mapped[str] = mapped_column(Text, nullable=False)
    edited_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    edited_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)

    acceptance_criterion: Mapped["AcceptanceCriterion"] = relationship(back_populates="edits")
