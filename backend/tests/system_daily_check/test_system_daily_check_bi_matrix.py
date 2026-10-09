from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from sqlalchemy import Column, Integer, MetaData, Table, create_engine
from sqlalchemy.orm import Session

from app.models import (
    Sucursal,
    SystemDailyCheckAnswerORM,
    SystemDailyCheckORM,
    SystemDailyCheckPromptStateORM,
    SystemDailyCheckRolloutBranchORM,
)
from app.services.system_daily_check_bi_service import (
    build_system_daily_check_bi_matrix,
)
from app.services.system_daily_check_service import QUESTIONS


def _engine():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("users", metadata, Column("id", Integer, primary_key=True))
    Sucursal.__table__.to_metadata(metadata)
    SystemDailyCheckRolloutBranchORM.__table__.to_metadata(metadata)
    SystemDailyCheckORM.__table__.to_metadata(metadata)
    SystemDailyCheckAnswerORM.__table__.to_metadata(metadata)
    SystemDailyCheckPromptStateORM.__table__.to_metadata(metadata)

    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        metadata.create_all(connection)
        connection.exec_driver_sql("INSERT INTO users (id) VALUES (1)")
        for branch_id, name in ((10, "ALFA"), (11, "BETA")):
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


def test_matrix_distinguishes_failure_na_and_pending():
    engine = _engine()
    business_date = date(2026, 10, 9)
    try:
        with Session(engine) as session:
            session.add_all(
                [
                    SystemDailyCheckRolloutBranchORM(
                        sucursal_id=10,
                        enabled_from=business_date,
                        configured_by_user_id=1,
                    ),
                    SystemDailyCheckRolloutBranchORM(
                        sucursal_id=11,
                        enabled_from=business_date,
                        configured_by_user_id=1,
                    ),
                ]
            )
            check = SystemDailyCheckORM(
                id=1,
                sucursal_id=10,
                business_date=business_date,
                performed_by_user_id=1,
                general_status="MINOR_FAILURE",
                submitted_at=datetime(
                    2026, 10, 9, 16, 0,
                    tzinfo=timezone.utc,
                ),
            )
            session.add(check)
            session.flush()

            for index, question in enumerate(QUESTIONS, start=1):
                value = "YES"
                if question.key == "GASCA_WORKING":
                    value = "NO"
                elif question.key == "AMBIENT_AUDIO_WORKING":
                    value = "NA"
                session.add(
                    SystemDailyCheckAnswerORM(
                        id=index,
                        check_id=1,
                        question_key=question.key,
                        question_label_snapshot=question.label,
                        category_key=question.category_key,
                        answer=value,
                    )
                )

            session.add_all(
                [
                    SystemDailyCheckPromptStateORM(
                        sucursal_id=10,
                        business_date=business_date,
                        postpone_count=1,
                    ),
                    SystemDailyCheckPromptStateORM(
                        sucursal_id=11,
                        business_date=business_date,
                        postpone_count=2,
                    ),
                ]
            )
            session.commit()

        with Session(engine) as session:
            result = build_system_daily_check_bi_matrix(
                _actor(),
                business_date=business_date,
                session=session,
            )

        assert len(result["rows"]) == 2
        by_branch = {
            row["sucursal_id"]: row
            for row in result["rows"]
        }

        alpha = by_branch[10]
        assert alpha["check_id"] == 1
        assert alpha["postpone_count"] == 1
        assert alpha["cells"]["COMPUTING"]["state"] == "GREEN"
        assert alpha["cells"]["INTERNET"]["state"] == "GREEN"
        assert alpha["cells"]["BI_REPORTS"]["state"] == "GREEN"
        assert alpha["cells"]["GASCA"] == {
            "state": "YELLOW",
            "label": "Falla menor",
        }
        assert alpha["cells"]["AUDIO"] == {
            "state": "NA",
            "label": "No aplica",
        }
        assert alpha["cells"]["GENERAL"]["state"] == "YELLOW"

        beta = by_branch[11]
        assert beta["check_id"] is None
        assert beta["postpone_count"] == 2
        assert {
            cell["state"]
            for cell in beta["cells"].values()
        } == {"PENDING"}
    finally:
        engine.dispose()
