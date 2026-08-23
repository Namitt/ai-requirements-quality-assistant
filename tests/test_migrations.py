from __future__ import annotations

import sqlite3

import pytest
from alembic import command
from alembic.config import Config


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
