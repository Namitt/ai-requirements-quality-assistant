"""acceptance criteria module

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-23

"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "extracted_acceptance_criteria",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("requirement_id", sa.Integer(), nullable=False),
        sa.Column("criterion_text", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("replayed_from_id", sa.Integer(), nullable=True),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["requirement_id"], ["requirements.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["replayed_from_id"],
            ["extracted_acceptance_criteria.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "mode IN ('live','replay')", name="ck_extracted_acceptance_criteria_mode"
        ),
        sa.CheckConstraint(
            "(mode = 'live' AND replayed_from_id IS NULL) "
            "OR (mode = 'replay' AND replayed_from_id IS NOT NULL)",
            name="ck_extracted_acceptance_criteria_replay_pairing",
        ),
    )

    op.create_table(
        "acceptance_criteria",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_extraction_id", sa.Integer(), nullable=False),
        sa.Column("current_text", sa.Text(), nullable=False),
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
            ["extracted_acceptance_criteria.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "validation_state IN ('not_validated','pass','warn','fail')",
            name="ck_acceptance_criteria_validation_state",
        ),
        sa.CheckConstraint(
            "review_status IN ('pending','approved','rejected')",
            name="ck_acceptance_criteria_review_status",
        ),
        sa.CheckConstraint(
            "review_status != 'approved' OR validation_state != 'fail'",
            name="ck_acceptance_criteria_fail_blocks_approval",
        ),
        sa.CheckConstraint(
            "review_status != 'approved' OR validation_state != 'warn' "
            "OR warn_acknowledged_at IS NOT NULL",
            name="ck_acceptance_criteria_warn_requires_ack",
        ),
    )

    op.create_table(
        "acceptance_criteria_edits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("acceptance_criterion_id", sa.Integer(), nullable=False),
        sa.Column("previous_text", sa.Text(), nullable=False),
        sa.Column("new_text", sa.Text(), nullable=False),
        sa.Column("edited_by", sa.Text(), nullable=True),
        sa.Column("edited_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["acceptance_criterion_id"], ["acceptance_criteria.id"], ondelete="RESTRICT"
        ),
    )

    with op.batch_alter_table("validation_runs") as batch_op:
        batch_op.alter_column("requirement_id", existing_type=sa.Integer(), nullable=True)
        batch_op.add_column(sa.Column("acceptance_criterion_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_validation_runs_acceptance_criterion_id",
            "acceptance_criteria",
            ["acceptance_criterion_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_check_constraint(
            "ck_validation_runs_exactly_one_parent",
            "(requirement_id IS NOT NULL AND acceptance_criterion_id IS NULL) "
            "OR (requirement_id IS NULL AND acceptance_criterion_id IS NOT NULL)",
        )


def downgrade() -> None:
    with op.batch_alter_table("validation_runs") as batch_op:
        batch_op.drop_constraint("ck_validation_runs_exactly_one_parent", type_="check")
        batch_op.drop_constraint(
            "fk_validation_runs_acceptance_criterion_id", type_="foreignkey"
        )
        batch_op.drop_column("acceptance_criterion_id")
        batch_op.alter_column("requirement_id", existing_type=sa.Integer(), nullable=False)

    op.drop_table("acceptance_criteria_edits")
    op.drop_table("acceptance_criteria")
    op.drop_table("extracted_acceptance_criteria")
