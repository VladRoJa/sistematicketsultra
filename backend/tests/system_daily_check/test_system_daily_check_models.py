from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    SystemDailyCheckAffectedScope,
    SystemDailyCheckAnswerORM,
    SystemDailyCheckAnswerValue,
    SystemDailyCheckGeneralStatus,
    SystemDailyCheckIssueAttachmentORM,
    SystemDailyCheckIssueORM,
    SystemDailyCheckORM,
    SystemDailyCheckPromptStateORM,
)


def _engine():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("users", metadata, Column("id", Integer, primary_key=True))
    Table(
        "sucursales",
        metadata,
        Column("sucursal_id", Integer, primary_key=True),
    )
    SystemDailyCheckORM.__table__.to_metadata(metadata)
    SystemDailyCheckAnswerORM.__table__.to_metadata(metadata)
    SystemDailyCheckIssueORM.__table__.to_metadata(metadata)
    SystemDailyCheckIssueAttachmentORM.__table__.to_metadata(metadata)
    SystemDailyCheckPromptStateORM.__table__.to_metadata(metadata)

    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        metadata.create_all(connection)
        connection.exec_driver_sql(
            "INSERT INTO users (id) VALUES (1), (2)"
        )
        connection.exec_driver_sql(
            "INSERT INTO sucursales (sucursal_id) VALUES (10), (11)"
        )
    return engine


def _check(**overrides):
    values = {
        "id": 1,
        "sucursal_id": 10,
        "business_date": date(2026, 10, 9),
        "performed_by_user_id": 1,
        "general_status": SystemDailyCheckGeneralStatus.NORMAL,
    }
    values.update(overrides)
    return SystemDailyCheckORM(**values)


def _answer(**overrides):
    values = {
        "id": 1,
        "check_id": 1,
        "question_key": "COMPUTERS_WORKING",
        "question_label_snapshot": (
            "¿Las computadoras de la sucursal funcionan correctamente?"
        ),
        "category_key": "COMPUTING",
        "answer": SystemDailyCheckAnswerValue.YES,
    }
    values.update(overrides)
    return SystemDailyCheckAnswerORM(**values)


def test_catalog_values_match_m1_contract():
    assert SystemDailyCheckAnswerValue.ALL == ("YES", "NO", "NA")
    assert SystemDailyCheckGeneralStatus.ALL == (
        "NORMAL",
        "MINOR_FAILURE",
        "OPERATIONAL_IMPACT",
    )
    assert SystemDailyCheckAffectedScope.ALL == ("ONE", "MULTIPLE")


def test_tables_are_independent_from_ticket_v1():
    tables = {
        SystemDailyCheckORM.__tablename__,
        SystemDailyCheckAnswerORM.__tablename__,
        SystemDailyCheckIssueORM.__tablename__,
        SystemDailyCheckIssueAttachmentORM.__tablename__,
        SystemDailyCheckPromptStateORM.__tablename__,
    }
    assert tables == {
        "system_daily_checks",
        "system_daily_check_answers",
        "system_daily_check_issues",
        "system_daily_check_issue_attachments",
        "system_daily_check_prompt_states",
    }

    fk_targets = {
        fk.target_fullname
        for table in (
            SystemDailyCheckORM.__table__,
            SystemDailyCheckAnswerORM.__table__,
            SystemDailyCheckIssueORM.__table__,
            SystemDailyCheckIssueAttachmentORM.__table__,
            SystemDailyCheckPromptStateORM.__table__,
        )
        for fk in table.foreign_keys
    }
    assert all(not target.startswith("tickets.") for target in fk_targets)
    assert "users.id" in fk_targets
    assert "sucursales.sucursal_id" in fk_targets
    assert "system_daily_checks.id" in fk_targets
    assert "system_daily_check_answers.id" in fk_targets
    assert "system_daily_check_issues.id" in fk_targets


def test_database_enforces_one_check_per_branch_and_business_date():
    engine = _engine()
    try:
        with Session(engine) as session:
            session.add(_check())
            session.commit()

        with Session(engine) as session:
            session.add(_check(id=2, performed_by_user_id=2))
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

        with Session(engine) as session:
            session.add(
                _check(
                    id=3,
                    sucursal_id=11,
                    performed_by_user_id=2,
                )
            )
            session.commit()
    finally:
        engine.dispose()


def test_database_enforces_answer_domain_and_question_uniqueness():
    engine = _engine()
    try:
        with Session(engine) as session:
            session.add(_check())
            session.flush()
            session.add(_answer())
            session.commit()

        with Session(engine) as session:
            session.add(_answer(id=2, answer=SystemDailyCheckAnswerValue.NA))
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

        with Session(engine) as session:
            session.add(
                _answer(
                    id=3,
                    question_key="INTERNET_WORKING",
                    question_label_snapshot="¿Las computadoras tienen conexión a internet?",
                    answer="INVALID",
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    finally:
        engine.dispose()


def test_database_enforces_issue_constraints():
    engine = _engine()
    try:
        with Session(engine) as session:
            session.add(_check())
            session.flush()
            session.add(
                _answer(
                    answer=SystemDailyCheckAnswerValue.NO,
                )
            )
            session.flush()
            session.add(
                SystemDailyCheckIssueORM(
                    id=1,
                    answer_id=1,
                    affected_scope=SystemDailyCheckAffectedScope.ONE,
                    reported_to_support=False,
                    description="La computadora no enciende.",
                )
            )
            session.commit()

        with Session(engine) as session:
            session.add(
                _answer(
                    id=2,
                    question_key="CAMERAS_WORKING",
                    question_label_snapshot="¿El sistema de cámaras funciona?",
                    answer=SystemDailyCheckAnswerValue.NO,
                )
            )
            session.flush()
            session.add(
                SystemDailyCheckIssueORM(
                    id=2,
                    answer_id=2,
                    affected_scope="INVALID",
                    reported_to_support=True,
                    description="Sin señal.",
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

        with Session(engine) as session:
            session.add(
                _answer(
                    id=3,
                    question_key="INTERNET_WORKING",
                    question_label_snapshot="¿Las computadoras tienen conexión a internet?",
                    answer=SystemDailyCheckAnswerValue.NO,
                )
            )
            session.flush()
            session.add(
                SystemDailyCheckIssueORM(
                    id=3,
                    answer_id=3,
                    affected_scope=None,
                    reported_to_support=False,
                    description="   ",
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    finally:
        engine.dispose()


def test_database_enforces_issue_attachment_metadata_constraints():
    engine = _engine()
    try:
        with Session(engine) as session:
            session.add(_check())
            session.flush()
            session.add(
                _answer(
                    answer=SystemDailyCheckAnswerValue.NO,
                )
            )
            session.flush()
            session.add(
                SystemDailyCheckIssueORM(
                    id=1,
                    answer_id=1,
                    affected_scope=SystemDailyCheckAffectedScope.ONE,
                    reported_to_support=True,
                    description="Falla visible.",
                )
            )
            session.flush()
            session.add(
                SystemDailyCheckIssueAttachmentORM(
                    id=1,
                    issue_id=1,
                    original_filename="evidencia.jpg",
                    storage_key="system-daily-checks/1/evidencia.jpg",
                    mime_type="image/jpeg",
                    file_size_bytes=1234,
                    sha256="a" * 64,
                    uploaded_by_user_id=1,
                )
            )
            session.commit()

        with Session(engine) as session:
            session.add(
                SystemDailyCheckIssueAttachmentORM(
                    id=2,
                    issue_id=1,
                    original_filename="duplicada.jpg",
                    storage_key="system-daily-checks/1/evidencia.jpg",
                    mime_type="image/jpeg",
                    file_size_bytes=1234,
                    sha256="b" * 64,
                    uploaded_by_user_id=2,
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

        with Session(engine) as session:
            session.add(
                SystemDailyCheckIssueAttachmentORM(
                    id=3,
                    issue_id=1,
                    original_filename="mala.jpg",
                    storage_key="system-daily-checks/1/mala.jpg",
                    mime_type="image/jpeg",
                    file_size_bytes=-1,
                    sha256="bad",
                    uploaded_by_user_id=1,
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    finally:
        engine.dispose()


def test_database_enforces_prompt_state_unique_branch_date_and_two_postpones():
    engine = _engine()
    try:
        with Session(engine) as session:
            session.add(
                SystemDailyCheckPromptStateORM(
                    id=1,
                    sucursal_id=10,
                    business_date=date(2026, 10, 9),
                    postpone_count=2,
                )
            )
            session.commit()

        with Session(engine) as session:
            session.add(
                SystemDailyCheckPromptStateORM(
                    id=2,
                    sucursal_id=10,
                    business_date=date(2026, 10, 10),
                    postpone_count=3,
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

        with Session(engine) as session:
            session.add(
                SystemDailyCheckPromptStateORM(
                    id=3,
                    sucursal_id=10,
                    business_date=date(2026, 10, 9),
                    postpone_count=0,
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    finally:
        engine.dispose()
