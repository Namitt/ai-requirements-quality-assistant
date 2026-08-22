"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-08-22

"""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "extraction_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_document_id", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("replayed_from_run_id", sa.Integer(), nullable=True),
        sa.Column("raw_response", sa.Text(), nullable=True),
        sa.Column("run_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_document_id"], ["source_documents.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["replayed_from_run_id"], ["extraction_runs.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "mode IN ('live','replay')", name="ck_extraction_runs_mode"
        ),
        sa.CheckConstraint(
            "(mode = 'live' AND replayed_from_run_id IS NULL) "
            "OR (mode = 'replay' AND replayed_from_run_id IS NOT NULL)",
            name="ck_extraction_runs_replay_pairing",
        ),
    )

    op.create_table(
        "extracted_requirements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("extraction_run_id", sa.Integer(), nullable=False),
        sa.Column("requirement_text", sa.Text(), nullable=False),
        sa.Column("source_span_start", sa.Integer(), nullable=False),
        sa.Column("source_span_end", sa.Integer(), nullable=False),
        sa.Column("source_quote", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["extraction_run_id"], ["extraction_runs.id"], ondelete="RESTRICT"
        ),
    )

    op.create_table(
        "requirements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_extraction_id", sa.Integer(), nullable=True),
        sa.Column("current_text", sa.Text(), nullable=False),
        sa.Column("origin", sa.Text(), nullable=False),
        sa.Column(
            "validation_state",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'not_validated'"),
        ),
        sa.Column(
            "review_status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("warn_acknowledged_at", sa.DateTime(), nullable=True),
        sa.Column("warn_acknowledged_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_extraction_id"],
            ["extracted_requirements.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "origin IN ('ai_generated','manual')", name="ck_requirements_origin"
        ),
        sa.CheckConstraint(
            "validation_state IN ('not_validated','pass','warn','fail')",
            name="ck_requirements_validation_state",
        ),
        sa.CheckConstraint(
            "review_status IN ('pending','approved','rejected')",
            name="ck_requirements_review_status",
        ),
        sa.CheckConstraint(
            "review_status != 'approved' OR validation_state != 'fail'",
            name="ck_requirements_fail_blocks_approval",
        ),
        sa.CheckConstraint(
            "review_status != 'approved' OR validation_state != 'warn' "
            "OR warn_acknowledged_at IS NOT NULL",
            name="ck_requirements_warn_requires_ack",
        ),
    )

    op.create_table(
        "requirement_edits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("requirement_id", sa.Integer(), nullable=False),
        sa.Column("previous_text", sa.Text(), nullable=False),
        sa.Column("new_text", sa.Text(), nullable=False),
        sa.Column("edited_by", sa.Text(), nullable=True),
        sa.Column("edited_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["requirement_id"], ["requirements.id"], ondelete="RESTRICT"
        ),
    )

    op.create_table(
        "validation_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("default_severity", sa.Text(), nullable=False),
        sa.UniqueConstraint("code", name="uq_validation_rules_code"),
        sa.CheckConstraint(
            "default_severity IN ('warn','fail')",
            name="ck_validation_rules_default_severity",
        ),
    )

    op.create_table(
        "validation_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("requirement_id", sa.Integer(), nullable=False),
        sa.Column("validator_version", sa.Text(), nullable=False),
        sa.Column("run_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["requirement_id"], ["requirements.id"], ondelete="RESTRICT"
        ),
    )

    op.create_table(
        "validation_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("validation_run_id", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.Integer(), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("recommended_action", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["validation_run_id"], ["validation_runs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"], ["validation_rules.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "result IN ('pass','warn','fail')", name="ck_validation_results_result"
        ),
        sa.UniqueConstraint(
            "validation_run_id", "rule_id", name="uq_validation_results_run_rule"
        ),
    )


def downgrade() -> None:
    op.drop_table("validation_results")
    op.drop_table("validation_runs")
    op.drop_table("validation_rules")
    op.drop_table("requirement_edits")
    op.drop_table("requirements")
    op.drop_table("extracted_requirements")
    op.drop_table("extraction_runs")
    op.drop_table("source_documents")
