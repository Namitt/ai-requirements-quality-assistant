"""not_validated blocks approval

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-23

"""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("requirements") as batch_op:
        batch_op.create_check_constraint(
            "ck_requirements_not_validated_blocks_approval",
            "review_status != 'approved' OR validation_state != 'not_validated'",
        )

    with op.batch_alter_table("acceptance_criteria") as batch_op:
        batch_op.create_check_constraint(
            "ck_acceptance_criteria_not_validated_blocks_approval",
            "review_status != 'approved' OR validation_state != 'not_validated'",
        )


def downgrade() -> None:
    with op.batch_alter_table("acceptance_criteria") as batch_op:
        batch_op.drop_constraint(
            "ck_acceptance_criteria_not_validated_blocks_approval", type_="check"
        )

    with op.batch_alter_table("requirements") as batch_op:
        batch_op.drop_constraint(
            "ck_requirements_not_validated_blocks_approval", type_="check"
        )
