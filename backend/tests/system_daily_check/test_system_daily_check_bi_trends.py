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
    build_system_daily_check_bi_trends,
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
        connection.exec_driver_sql("INSERT INTO users (id) VALUES (1)")
        connection.exec_driver_sql(
            """
            INSERT INTO sucursales (
                sucursal_id, serie, sucursal, estado,
                operational_status, is_demo, municipio, direccion
            )
            VALUES
                (10, 'S10', 'ALFA', 'BC', 'ACTIVA', 0, 'MEXICALI', 'N/A')
            """
        )
    return engine


def _actor():
    return SimpleNamespace(
        id=1,
        username="SISTEMAS",
        rol="SISTEMAS",
    )


def _check(
    check_id,
    business_date,
    status,
    hour=16,
):
    return SystemDailyCheckORM(
        id=check_id,
        sucursal_id=10,
        business_date=business_date,
        performed_by_user_id=1,
        general_status=status,
        submitted_at=datetime(
            business_date.year,
            business_date.month,
            business_date.day,
            hour,
            0,
            tzinfo=timezone.utc,
        ),
    )


def _no_answer(
    answer_id,
    check_id,
    key,
    label,
):
    return SystemDailyCheckAnswerORM(
        id=answer_id,
        check_id=check_id,
        question_key=key,
        question_label_snapshot=label,
        category_key="TEST",
        answer="NO",
    )


def _seed(session: Session):
    start = date(2026, 10, 4)
    session.add(
        SystemDailyCheckRolloutBranchORM(
            sucursal_id=10,
            enabled_from=start,
            configured_by_user_id=1,
        )
    )
    session.add_all(
        [
            _check(1, date(2026, 10, 4), "NORMAL"),
            _check(2, date(2026, 10, 5), "MINOR_FAILURE"),
            _check(3, date(2026, 10, 10), "MINOR_FAILURE", hour=18),
            _check(4, date(2026, 10, 11), "OPERATIONAL_IMPACT"),
        ]
    )
    session.flush()

    session.add_all(
        [
            _no_answer(
                1,
                2,
                "GASCA_WORKING",
                "¿Gasca permite trabajar?",
            ),
            _no_answer(
                2,
                3,
                "GASCA_WORKING",
                "¿Gasca permite trabajar?",
            ),
            _no_answer(
                3,
                4,
                "INTERNET_WORKING",
                "¿Hay conexión a internet?",
            ),
        ]
    )
    session.flush()

    session.add_all(
        [
            SystemDailyCheckIssueORM(
                id=1,
                answer_id=1,
                reported_to_support=False,
                description="Gasca no abre.",
            ),
            SystemDailyCheckIssueORM(
                id=2,
                answer_id=2,
                reported_to_support=True,
                description="Gasca no abre.",
            ),
            SystemDailyCheckIssueORM(
                id=3,
                answer_id=3,
                reported_to_support=True,
                affected_scope="MULTIPLE",
                description="Sin internet.",
            ),
        ]
    )

    session.add_all(
        [
            SystemDailyCheckPromptStateORM(
                sucursal_id=10,
                business_date=date(2026, 10, 4),
                postpone_count=0,
            ),
            SystemDailyCheckPromptStateORM(
                sucursal_id=10,
                business_date=date(2026, 10, 5),
                postpone_count=1,
            ),
            SystemDailyCheckPromptStateORM(
                sucursal_id=10,
                business_date=date(2026, 10, 10),
                postpone_count=2,
                mandatory_from_at=datetime(
                    2026, 10, 10, 17, 0,
                    tzinfo=timezone.utc,
                ),
            ),
            SystemDailyCheckPromptStateORM(
                sucursal_id=10,
                business_date=date(2026, 10, 11),
                postpone_count=2,
                mandatory_from_at=datetime(
                    2026, 10, 11, 17, 0,
                    tzinfo=timezone.utc,
                ),
            ),
        ]
    )
    session.commit()


def test_week_trend_uses_sunday_saturday_and_source_counts():
    engine = _engine()
    try:
        with Session(engine) as session:
            _seed(session)

        with Session(engine) as session:
            result = build_system_daily_check_bi_trends(
                _actor(),
                date_from=date(2026, 10, 4),
                date_to=date(2026, 10, 11),
                granularity="WEEK",
                now=datetime(
                    2026, 10, 11, 16, 30,
                    tzinfo=timezone.utc,
                ),
                session=session,
            )

        assert result["filters"]["week_convention"] == (
            "SUNDAY_TO_SATURDAY"
        )
        assert len(result["trend"]) == 2

        week_one = result["trend"][0]
        assert week_one["period_start"] == "2026-10-04"
        assert week_one["period_end"] == "2026-10-10"
        assert week_one["expected"] == 7
        assert week_one["completed"] == 3
        assert week_one["pending"] == 4
        assert week_one["compliance_pct"] == 42.9
        assert week_one["normal"] == 1
        assert week_one["minor_failure"] == 2
        assert week_one["operational_impact"] == 0
        assert week_one["no_answers"] == 2
        assert week_one["issues_total"] == 2
        assert week_one["reported"] == 1
        assert week_one["unreported"] == 1
        assert week_one["reported_pct"] == 50.0
        assert week_one["completed_without_postpone"] == 1
        assert week_one["completed_after_1"] == 1
        assert week_one["completed_after_2"] == 1
        assert week_one["reached_mandatory"] == 1

        week_two = result["trend"][1]
        assert week_two["period_start"] == "2026-10-11"
        assert week_two["expected"] == 1
        assert week_two["completed"] == 1
        assert week_two["operational_impact"] == 1
        assert week_two["reported_pct"] == 100.0
        assert week_two["reached_mandatory"] == 0

        gasca = result["question_ranking"][0]
        assert gasca["question_key"] == "GASCA_WORKING"
        assert gasca["no_answers"] == 2
        assert gasca["distinct_days"] == 2
        assert gasca["reported_pct"] == 50.0

        branch = result["branch_ranking"][0]
        assert branch["sucursal_id"] == 10
        assert branch["expected"] == 8
        assert branch["completed"] == 4
        assert branch["pending"] == 4
        assert branch["checks_with_failure"] == 3
        assert branch["no_answers"] == 3
        assert branch["issues_total"] == 3
        assert branch["reported_pct"] == 66.7

        assert result["recurrence"] == [
            {
                "sucursal_id": 10,
                "sucursal": "ALFA",
                "question_key": "GASCA_WORKING",
                "question_label": "¿Gasca permite trabajar?",
                "distinct_days": 2,
                "first_business_date": "2026-10-05",
                "last_business_date": "2026-10-10",
            }
        ]
    finally:
        engine.dispose()


def test_day_week_month_granularities_are_explicit():
    engine = _engine()
    try:
        with Session(engine) as session:
            _seed(session)

        with Session(engine) as session:
            day = build_system_daily_check_bi_trends(
                _actor(),
                date_from=date(2026, 10, 4),
                date_to=date(2026, 10, 11),
                granularity="DAY",
                session=session,
            )
            week = build_system_daily_check_bi_trends(
                _actor(),
                date_from=date(2026, 10, 4),
                date_to=date(2026, 10, 11),
                granularity="WEEK",
                session=session,
            )
            month = build_system_daily_check_bi_trends(
                _actor(),
                date_from=date(2026, 10, 4),
                date_to=date(2026, 10, 11),
                granularity="MONTH",
                session=session,
            )

        assert len(day["trend"]) == 8
        assert len(week["trend"]) == 2
        assert len(month["trend"]) == 1
        assert month["trend"][0]["period_start"] == "2026-10-01"
        assert month["trend"][0]["period_end"] == "2026-10-31"
        assert month["trend"][0]["expected"] == 8
        assert month["trend"][0]["completed"] == 4
    finally:
        engine.dispose()
