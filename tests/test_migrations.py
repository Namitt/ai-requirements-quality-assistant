from __future__ import annotations

import sqlite3

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import sessionmaker

from app.acceptance_criteria_validation_engine import EXPECTED_AC_RULE_CODES
from app.db import get_engine
from app.models import Requirement
from app.validation_engine import EXPECTED_RULE_CODES, run_validation


@pytest.fixture()
def alembic_config(tmp_path):
    db_path = tmp_path / "migration_test.db"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg, db_path


def test_full_upgrade_downgrade_cycle(alembic_config):
    cfg, db_path = alembic_config

    command.upgrade(cfg, "0001")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0002")
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT sql FROM sqlite_master WHERE name='requirements'")
    requirements_ddl = cur.fetchone()[0]
    cur.execute("SELECT sql FROM sqlite_master WHERE name='acceptance_criteria'")
    acceptance_criteria_ddl = cur.fetchone()[0]
    conn.close()

    assert "ck_requirements_not_validated_blocks_approval" in requirements_ddl
    assert "ck_acceptance_criteria_not_validated_blocks_approval" in acceptance_criteria_ddl


def test_0003_rejects_raw_insert_of_approved_not_validated_row(alembic_config):
    cfg, db_path = alembic_config
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(db_path)
    with pytest.raises(sqlite3.IntegrityError, match="ck_requirements_not_validated_blocks_approval"):
        conn.execute(
            "INSERT INTO requirements "
            "(current_text, origin, validation_state, review_status, created_at, updated_at) "
            "VALUES ('x', 'manual', 'not_validated', 'approved', datetime('now'), datetime('now'))"
        )
    conn.close()


def test_0003_remediates_pre_existing_invalid_requirement_row(alembic_config):
    cfg, db_path = alembic_config
    command.upgrade(cfg, "0002")

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO requirements "
        "(current_text, origin, validation_state, review_status, created_at, updated_at) "
        "VALUES ('legacy bad row', 'manual', 'not_validated', 'approved', "
        "datetime('now'), datetime('now'))"
    )
    conn.commit()
    conn.close()

    command.upgrade(cfg, "0003")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT review_status, validation_state FROM requirements "
        "WHERE current_text = 'legacy bad row'"
    )
    review_status, validation_state = cur.fetchone()
    conn.close()

    assert review_status == "pending"
    assert validation_state == "not_validated"


def test_0003_remediates_pre_existing_invalid_acceptance_criterion_row(alembic_config):
    cfg, db_path = alembic_config
    command.upgrade(cfg, "0002")

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO requirements "
        "(current_text, origin, validation_state, review_status, created_at, updated_at) "
        "VALUES ('parent', 'manual', 'pass', 'pending', datetime('now'), datetime('now'))"
    )
    conn.execute(
        "INSERT INTO extracted_acceptance_criteria "
        "(requirement_id, criterion_text, mode, model_name, prompt_version, created_at) "
        "VALUES (1, 'Given X, when Y, then Z.', 'live', 'm', 'v1', datetime('now'))"
    )
    conn.execute(
        "INSERT INTO acceptance_criteria "
        "(source_extraction_id, current_text, validation_state, review_status, "
        "created_at, updated_at) "
        "VALUES (1, 'Given X, when Y, then Z.', 'not_validated', 'approved', "
        "datetime('now'), datetime('now'))"
    )
    conn.commit()
    conn.close()

    command.upgrade(cfg, "0003")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT review_status, validation_state FROM acceptance_criteria")
    review_status, validation_state = cur.fetchone()
    conn.close()

    assert review_status == "pending"
    assert validation_state == "not_validated"


def test_0003_leaves_valid_approved_rows_untouched(alembic_config):
    cfg, db_path = alembic_config
    command.upgrade(cfg, "0002")

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO requirements "
        "(current_text, origin, validation_state, review_status, created_at, updated_at) "
        "VALUES ('legitimately approved', 'manual', 'pass', 'approved', "
        "datetime('now'), datetime('now'))"
    )
    conn.commit()
    conn.close()

    command.upgrade(cfg, "0003")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT review_status, validation_state FROM requirements "
        "WHERE current_text = 'legitimately approved'"
    )
    review_status, validation_state = cur.fetchone()
    conn.close()

    assert review_status == "approved"
    assert validation_state == "pass"


# ---------------------------------------------------------------------------
# 0004: validation_rules catalog seeding
# ---------------------------------------------------------------------------


def test_fresh_database_has_no_validation_rules_before_migrating(alembic_config):
    cfg, db_path = alembic_config
    command.upgrade(cfg, "0003")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM validation_rules")
    count = cur.fetchone()[0]
    conn.close()

    assert count == 0


def test_head_migration_seeds_the_complete_validation_rules_catalog(alembic_config):
    cfg, db_path = alembic_config
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT code FROM validation_rules")
    seeded_codes = {row[0] for row in cur.fetchall()}
    conn.close()

    expected_codes = set(EXPECTED_RULE_CODES) | set(EXPECTED_AC_RULE_CODES)
    assert seeded_codes == expected_codes


def test_head_migration_seeds_existing_database_stranded_at_0003(alembic_config):
    # Simulates a database that was already created and migrated up to the
    # previous head (0003) before this fix existed, and therefore has an
    # empty validation_rules table - not just a brand new database.
    cfg, db_path = alembic_config
    command.upgrade(cfg, "0003")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM validation_rules")
    assert cur.fetchone()[0] == 0
    conn.close()

    command.upgrade(cfg, "head")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM validation_rules")
    count = cur.fetchone()[0]
    conn.close()

    assert count == len(EXPECTED_RULE_CODES) + len(EXPECTED_AC_RULE_CODES)


def test_seeding_migration_does_not_duplicate_rows_on_reapply(alembic_config):
    cfg, db_path = alembic_config
    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")  # re-applying head must be a no-op, not a duplicate insert

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT code, COUNT(*) FROM validation_rules GROUP BY code")
    counts = {code: count for code, count in cur.fetchall()}
    conn.close()

    assert all(count == 1 for count in counts.values())
    assert len(counts) == len(EXPECTED_RULE_CODES) + len(EXPECTED_AC_RULE_CODES)


def test_fresh_migrated_database_can_perform_a_real_validation_without_manual_seeding(
    alembic_config,
):
    # This is the exact failure this migration fixes: a database created
    # purely via `alembic upgrade head`, with no call to
    # app.seed.seed_validation_rules() anywhere, must be able to run a real
    # validation immediately.
    cfg, db_path = alembic_config
    command.upgrade(cfg, "head")

    engine = get_engine(f"sqlite:///{db_path}")
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_factory() as session:
        requirement = Requirement(
            current_text="The system shall lock the account.", origin="manual"
        )
        session.add(requirement)
        session.commit()
        requirement_id = requirement.id

    with session_factory() as session:
        updated = run_validation(session, requirement_id)

    assert updated.validation_state in ("pass", "warn", "fail")
    engine.dispose()
