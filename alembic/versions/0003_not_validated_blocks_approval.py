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
    # A pre-fix application bug (see the P0 fix in this project's history)
    # could have let a requirement or acceptance criterion be approved while
    # still validation_state='not_validated'. That combination is exactly
    # what this migration's new CHECK constraints forbid, so any such row
    # left over from before the application-layer fix must be remediated
    # before the constraint is added, or the batch table-recreate below
    # would fail with an IntegrityError on any database that ever hit that
    # bug. Resetting review_status to 'pending' is the safe, conservative
    # choice: it is the state the corrected application logic would have
    # left the record in, and it requires the analyst to make a fresh,
    # informed approval decision rather than silently granting it one.
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "UPDATE requirements SET review_status = 'pending' "
            "WHERE review_status = 'approved' AND validation_state = 'not_validated'"
        )
    )
    connection.execute(
        sa.text(
            "UPDATE acceptance_criteria SET review_status = 'pending' "
            "WHERE review_status = 'approved' AND validation_state = 'not_validated'"
        )
    )

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
