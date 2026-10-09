from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from sqlalchemy import Column, Integer, MetaData, Table, create_engine
from sqlalchemy.orm import Session

from app.models import (
    Sucursal,
    SystemDailyCheckAnswerORM,
    SystemDailyCheckIssueORM,
    SystemDailyCheckORM,
    SystemDailyCheckPromptStateORM,
    SystemDailyCheckRolloutBranchORM,
)
from app.services.system_daily_check_bi_service import (
    build_system_daily_check_bi_summary,
)


def _engine():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table(
        "users",
        metadata,
        Column("id", Integer, primary_key=True),
    )
    Sucursal.__table__.to_metadata(metadata)
    SystemDailyCheckRolloutBranchORM.__table__.to_metadata(metadata)
    SystemDailyCheckORM.__table__.to_metadata(metadata)
    SystemDailyCheckAnswerORM.__table__.to_metadata(metadata)
    SystemDailyCheckIssueORM.__table__.to_metadata(metadata)
    SystemDailyCheckPromptStateORM.__table__.to_metadata(metadata)

    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        metadata.create_all(connection)
        connection.exec_driver_sql(
            "INSERT INTO users (id) VALUES (1), (2)"
        )
        for branch_id, name in (
            (10, "ACTIVA A"),
            (11, "ACTIVA B"),
            (12, "FUERA ROLLOUT"),
        ):
            connection.exec_driver_sql(
                """
                INSERT INTO sucursales (
                    sucursal_id,
                    serie,
                    sucursal,
                    estado,
                    operational_status,
                    is_demo,
                    municipio,
                    direccion
                )
                VALUES (?, ?, ?, 'BC', 'ACTIVA', 0, 'MEXICALI', 'N/A')
                """,
                (branch_id, f"S{branch_id}", name),
            )
    return engine


def _actor():
    return SimpleNamespace(
        id=1,
        username="SISTEMAS",
        rol="SISTEMAS",
    )


def _check(
    *,
    check_id,
    branch_id,
    business_date,
    status,
    submitted_at,
):
    return SystemDailyCheckORM(
        id=check_id,
        sucursal_id=branch_id,
        business_date=business_date,
        performed_by_user_id=1,
        general_status=status,
        submitted_at=submitted_at,
        created_at=submitted_at,
    )


def _answer(
    *,
    answer_id,
    check_id,
    question_key,
    answer,
):
    return SystemDailyCheckAnswerORM(
        id=answer_id,
        check_id=check_id,
        question_key=question_key,
        question_label_snapshot=question_key,
        category_key="TEST",
        answer=answer,
    )


def test_summary_matches_manual_branch_day_fixture():
    engine = _engine()
    day_one = date(2026, 10, 9)
    day_two = date(2026, 10, 10)
    try:
        with Session(engine) as session:
            session.add_all(
                [
                    SystemDailyCheckRolloutBranchORM(
                        sucursal_id=10,
                        enabled_from=day_one,
                        configured_by_user_id=1,
                    ),
                    SystemDailyCheckRolloutBranchORM(
                        sucursal_id=11,
                        enabled_from=day_one,
                        configured_by_user_id=1,
                    ),
                ]
            )
            session.add_all(
                [
                    _check(
                        check_id=1,
                        branch_id=10,
                        business_date=day_one,
                        status="NORMAL",
                        submitted_at=datetime(
                            2026, 10, 9, 16, 0,
                            tzinfo=timezone.utc,
                        ),
                    ),
                    _check(
                        check_id=2,
                        branch_id=10,
                        business_date=day_two,
                        status="MINOR_FAILURE",
                        submitted_at=datetime(
                            2026, 10, 10, 16, 0,
                            tzinfo=timezone.utc,
                        ),
                    ),
                    _check(
                        check_id=3,
                        branch_id=11,
                        business_date=day_two,
                        status="OPERATIONAL_IMPACT",
                        submitted_at=datetime(
                            2026, 10, 10, 17, 0,
                            tzinfo=timezone.utc,
                        ),
                    ),
                    _check(
                        check_id=4,
                        branch_id=12,
                        business_date=day_one,
                        status="NORMAL",
                        submitted_at=datetime(
                            2026, 10, 9, 16, 30,
                            tzinfo=timezone.utc,
                        ),
                    ),
                ]
            )
            session.flush()

            session.add_all(
                [
                    _answer(
                        answer_id=1,
                        check_id=1,
                        question_key="COMPUTERS_WORKING",
                        answer="YES",
                    ),
                    _answer(
                        answer_id=2,
                        check_id=1,
                        question_key="TV_SCREENS_WORKING",
                        answer="NA",
                    ),
                    _answer(
                        answer_id=3,
                        check_id=2,
                        question_key="GASCA_WORKING",
                        answer="NO",
                    ),
                    _answer(
                        answer_id=4,
                        check_id=2,
                        question_key="TV_SCREENS_WORKING",
                        answer="NA",
                    ),
                    _answer(
                        answer_id=5,
                        check_id=3,
                        question_key="INTERNET_WORKING",
                        answer="NO",
                    ),
                    _answer(
                        answer_id=6,
                        check_id=4,
                        question_key="GASCA_WORKING",
                        answer="NO",
                    ),
                ]
            )
            session.flush()
            session.add_all(
                [
                    SystemDailyCheckIssueORM(
                        id=1,
                        answer_id=3,
                        reported_to_support=False,
                        description="Gasca no abre.",
                    ),
                    SystemDailyCheckIssueORM(
                        id=2,
                        answer_id=5,
                        reported_to_support=True,
                        affected_scope="ONE",
                        description="Sin internet.",
                    ),
                    SystemDailyCheckIssueORM(
                        id=3,
                        answer_id=6,
                        reported_to_support=True,
                        description="Fuera de rollout.",
                    ),
                ]
            )
            session.add_all(
                [
                    SystemDailyCheckPromptStateORM(
                        sucursal_id=10,
                        business_date=day_one,
                        postpone_count=0,
                        completed_at=datetime(
                            2026, 10, 9, 16, 0,
                            tzinfo=timezone.utc,
                        ),
                    ),
                    SystemDailyCheckPromptStateORM(
                        sucursal_id=10,
                        business_date=day_two,
                        postpone_count=1,
                        completed_at=datetime(
                            2026, 10, 10, 16, 0,
                            tzinfo=timezone.utc,
                        ),
                    ),
                    SystemDailyCheckPromptStateORM(
                        sucursal_id=11,
                        business_date=day_two,
                        postpone_count=2,
                        mandatory_from_at=datetime(
                            2026, 10, 10, 16, 30,
                            tzinfo=timezone.utc,
                        ),
                        completed_at=datetime(
                            2026, 10, 10, 17, 0,
                            tzinfo=timezone.utc,
                        ),
                    ),
                ]
            )
            session.commit()

        with Session(engine) as session:
            result = build_system_daily_check_bi_summary(
                _actor(),
                date_from=day_one,
                date_to=day_two,
                now=datetime(
                    2026, 10, 11, 18, 0,
                    tzinfo=timezone.utc,
                ),
                session=session,
            )

        assert result["universe"] == {
            "expected_checklists": 4,
            "expected_branches": 2,
            "out_of_rollout_submissions": 1,
        }
        assert result["summary"] == {
            "completed": 3,
            "pending": 1,
            "compliance_pct": 75.0,
            "normal": 1,
            "minor_failure": 1,
            "operational_impact": 1,
        }
        assert result["failures"] == {
            "checks_with_failure": 2,
            "no_answers": 2,
            "issues_total": 2,
            "reported": 1,
            "unreported": 1,
            "reported_pct": 50.0,
        }
        assert result["postponements"] == {
            "completed_without_postpone": 1,
            "completed_after_1": 1,
            "completed_after_2": 1,
            "reached_mandatory": 1,
        }
    finally:
        engine.dispose()


def test_summary_without_expected_universe_is_explicit_na():
    engine = _engine()
    try:
        with Session(engine) as session:
            result = build_system_daily_check_bi_summary(
                _actor(),
                date_from=date(2026, 10, 9),
                date_to=date(2026, 10, 9),
                session=session,
            )
        assert result["universe"]["expected_checklists"] == 0
        assert result["summary"]["completed"] == 0
        assert result["summary"]["pending"] == 0
        assert result["summary"]["compliance_pct"] is None
        assert result["failures"]["reported_pct"] is None
    finally:
        engine.dispose()
