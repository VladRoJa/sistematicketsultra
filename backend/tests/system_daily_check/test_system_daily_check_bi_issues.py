from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from sqlalchemy import Column, Integer, MetaData, Table, create_engine
from sqlalchemy.orm import Session

from app.models import (
    Sucursal,
    SystemDailyCheckAnswerORM,
    SystemDailyCheckIssueAttachmentORM,
    SystemDailyCheckIssueORM,
    SystemDailyCheckORM,
    SystemDailyCheckRolloutBranchORM,
)
from app.services.system_daily_check_bi_service import (
    list_system_daily_check_bi_issues,
)


def _engine():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("users", metadata, Column("id", Integer, primary_key=True))
    Sucursal.__table__.to_metadata(metadata)
    SystemDailyCheckRolloutBranchORM.__table__.to_metadata(metadata)
    SystemDailyCheckORM.__table__.to_metadata(metadata)
    SystemDailyCheckAnswerORM.__table__.to_metadata(metadata)
    SystemDailyCheckIssueORM.__table__.to_metadata(metadata)
    SystemDailyCheckIssueAttachmentORM.__table__.to_metadata(metadata)

    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        metadata.create_all(connection)
        connection.exec_driver_sql("INSERT INTO users (id) VALUES (1)")
        for branch_id, name in ((10, "ALFA"), (11, "FUERA")):
            connection.exec_driver_sql(
                """
                INSERT INTO sucursales (
                    sucursal_id, serie, sucursal, estado,
                    operational_status, is_demo, municipio, direccion
                )
                VALUES (?, ?, ?, 'BC', 'ACTIVA', 0, 'MEXICALI', 'N/A')
                """,
                (branch_id, f"S{branch_id}", name),
            )
    return engine


def _actor():
    return SimpleNamespace(id=1, username="SISTEMAS", rol="SISTEMAS")


def test_issue_drilldown_reconciles_to_rollout_and_support_filter():
    engine = _engine()
    business_date = date(2026, 10, 9)
    submitted_at = datetime(
        2026, 10, 9, 16, 0, tzinfo=timezone.utc,
    )
    try:
        with Session(engine) as session:
            session.add(
                SystemDailyCheckRolloutBranchORM(
                    sucursal_id=10,
                    enabled_from=business_date,
                    configured_by_user_id=1,
                )
            )
            session.add_all(
                [
                    SystemDailyCheckORM(
                        id=1,
                        sucursal_id=10,
                        business_date=business_date,
                        performed_by_user_id=1,
                        general_status="MINOR_FAILURE",
                        submitted_at=submitted_at,
                    ),
                    SystemDailyCheckORM(
                        id=2,
                        sucursal_id=11,
                        business_date=business_date,
                        performed_by_user_id=1,
                        general_status="MINOR_FAILURE",
                        submitted_at=submitted_at,
                    ),
                ]
            )
            session.flush()
            session.add_all(
                [
                    SystemDailyCheckAnswerORM(
                        id=1,
                        check_id=1,
                        question_key="GASCA_WORKING",
                        question_label_snapshot="¿Gasca funciona?",
                        category_key="CONNECTIVITY_SYSTEMS",
                        answer="NO",
                    ),
                    SystemDailyCheckAnswerORM(
                        id=2,
                        check_id=1,
                        question_key="INTERNET_WORKING",
                        question_label_snapshot="¿Internet funciona?",
                        category_key="CONNECTIVITY_SYSTEMS",
                        answer="NO",
                    ),
                    SystemDailyCheckAnswerORM(
                        id=3,
                        check_id=2,
                        question_key="GASCA_WORKING",
                        question_label_snapshot="¿Gasca funciona?",
                        category_key="CONNECTIVITY_SYSTEMS",
                        answer="NO",
                    ),
                ]
            )
            session.flush()
            session.add_all(
                [
                    SystemDailyCheckIssueORM(
                        id=1,
                        answer_id=1,
                        reported_to_support=True,
                        description="Gasca no abre.",
                    ),
                    SystemDailyCheckIssueORM(
                        id=2,
                        answer_id=2,
                        reported_to_support=False,
                        affected_scope="ONE",
                        description="Sin internet.",
                    ),
                    SystemDailyCheckIssueORM(
                        id=3,
                        answer_id=3,
                        reported_to_support=True,
                        description="Fuera del rollout.",
                    ),
                ]
            )
            session.commit()

        with Session(engine) as session:
            all_rows = list_system_daily_check_bi_issues(
                _actor(),
                date_from=business_date,
                date_to=business_date,
                session=session,
            )
            assert all_rows["total"] == 2
            assert {
                row["issue_id"]
                for row in all_rows["items"]
            } == {1, 2}

            reported = list_system_daily_check_bi_issues(
                _actor(),
                date_from=business_date,
                date_to=business_date,
                reported_to_support=True,
                session=session,
            )
            assert reported["total"] == 1
            assert reported["items"][0]["issue_id"] == 1
            assert reported["items"][0]["check_id"] == 1
            assert reported["items"][0]["sucursal"] == "ALFA"

            unreported = list_system_daily_check_bi_issues(
                _actor(),
                date_from=business_date,
                date_to=business_date,
                reported_to_support=False,
                session=session,
            )
            assert unreported["total"] == 1
            assert unreported["items"][0]["issue_id"] == 2
    finally:
        engine.dispose()
