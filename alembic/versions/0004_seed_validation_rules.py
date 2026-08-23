"""seed validation rules catalog

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-23

"""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

# This is a deliberate, self-contained snapshot of the validation_rules
# catalog as of this migration's creation, not an import of
# app.seed.VALIDATION_RULES. Migrations in this project (see 0001-0003)
# never import application code - they are frozen records of what was
# applied at a point in time, and importing the live app.seed module here
# would mean a later edit to that module silently changes what this
# "historical" migration inserts for anyone running it fresh in the future.
# app/seed.py's seed_validation_rules() remains the source tests use for
# in-memory (Base.metadata.create_all) database setup; this migration is
# what guarantees the same catalog exists on a real database provisioned
# via `alembic upgrade head`, including one already sitting at revision
# 0003 with an empty validation_rules table.
VALIDATION_RULES = [
    {
        "code": "DUPLICATE_NEAR",
        "name": "Duplicate / near-duplicate",
        "description": (
            "Catch requirements that restate an existing one, creating "
            "redundant or conflicting requirements downstream."
        ),
        "default_severity": "fail",
    },
    {
        "code": "AMBIGUOUS_WORDING",
        "name": "Ambiguous wording",
        "description": "Flag subjective or untestable terms.",
        "default_severity": "warn",
    },
    {
        "code": "MISSING_ACCEPTANCE_CONDITION",
        "name": "Missing acceptance condition",
        "description": (
            "Flag requirements lacking a measurable or testable condition."
        ),
        "default_severity": "warn",
    },
    {
        "code": "MISSING_ACTOR",
        "name": "Missing actor",
        "description": (
            "Flag requirements with no clear subject performing the action."
        ),
        "default_severity": "warn",
    },
    {
        "code": "POSSIBLE_CONTRADICTION",
        "name": "Possible contradiction",
        "description": (
            "Surface requirement pairs that appear to set conflicting rules "
            "for the same subject. The highest-stakes issue in the set, and "
            "the least reliable to detect — must never be described as "
            '"contradiction detected," only as a possible contradiction '
            "requiring human judgement."
        ),
        "default_severity": "warn",
    },
    {
        "code": "AC_GIVEN_PRESENT",
        "name": "Given clause present",
        "description": "Flag acceptance criteria missing a Given clause.",
        "default_severity": "warn",
    },
    {
        "code": "AC_WHEN_PRESENT",
        "name": "When clause present",
        "description": "Flag acceptance criteria missing a When clause.",
        "default_severity": "warn",
    },
    {
        "code": "AC_THEN_PRESENT",
        "name": "Then clause present",
        "description": "Flag acceptance criteria missing a Then clause.",
        "default_severity": "warn",
    },
    {
        "code": "AC_MEASURABLE_THEN",
        "name": "Measurable Then condition",
        "description": (
            "Flag acceptance criteria whose Then clause lacks a measurable "
            "or testable condition."
        ),
        "default_severity": "warn",
    },
]


def upgrade() -> None:
    # INSERT OR IGNORE (backed by the existing uq_validation_rules_code
    # constraint from 0001) makes this safe to apply to a fresh database,
    # a pre-existing database already sitting at 0003 with zero rows, or -
    # defensively - a database that already has some/all of these codes
    # from another source: every code ends up present exactly once, with
    # no duplicate-key error and no double-insertion.
    connection = op.get_bind()
    insert_stmt = sa.text(
        "INSERT OR IGNORE INTO validation_rules "
        "(code, name, description, default_severity) "
        "VALUES (:code, :name, :description, :default_severity)"
    )
    for rule in VALIDATION_RULES:
        connection.execute(insert_stmt, rule)


def downgrade() -> None:
    # Only remove the exact rows this migration added, and only by the
    # codes it owns - never a blanket DELETE FROM validation_rules, which
    # could remove rows this migration did not create. The RESTRICT
    # foreign keys on validation_results.rule_id mean this will correctly
    # fail rather than silently succeed if any validation result still
    # references one of these rules.
    connection = op.get_bind()
    delete_stmt = sa.text("DELETE FROM validation_rules WHERE code = :code")
    for rule in VALIDATION_RULES:
        connection.execute(delete_stmt, {"code": rule["code"]})
