from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from sqlalchemy import Column, Integer, MetaData, Table, create_engine
from sqlalchemy.orm import Session

from app.models import (
    Sucursal,
    SystemDailyCheckORM,
    SystemDailyCheckPromptStateORM,
    SystemDailyCheckRolloutBranchORM,
)
from app.services.system_daily_check_bi_service import (
    list_system_daily_check_bi_pending,
)


def _engine():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("users", metadata, Column("id", Integer, primary_key=True))
    Sucursal.__table__.to_metadata(metadata)
    SystemDailyCheckRolloutBranchORM.__table__.to_metadata(metadata)
    SystemDailyCheckORM.__table__.to_metadata(metadata)
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


def test_pending_lists_expected_missing_branch_days():
    engine = _engine()
    try:
        with Session(engine) as session:
            session.add_all([
                SystemDailyCheckRolloutBranchORM(
                    sucursal_id=10,
                    enabled_from=date(2026, 10, 9),
                    configured_by_user_id=1,
                ),
                SystemDailyCheckRolloutBranchORM(
                    sucursal_id=11,
                    enabled_from=date(2026, 10, 9),
                    configured_by_user_id=1,
                ),
            ])
            session.add(
                SystemDailyCheckORM(
                    id=1,
                    sucursal_id=10,
                    business_date=date(2026, 10, 9),
                    performed_by_user_id=1,
                    general_status="NORMAL",
                )
            )
            session.add(
                SystemDailyCheckPromptStateORM(
                    sucursal_id=11,
                    business_date=date(2026, 10, 9),
                    postpone_count=2,
                    mandatory_from_at=datetime(
                        2026, 10, 9, 16, 30,
                        tzinfo=timezone.utc,
                    ),
                    next_prompt_at=datetime(
                        2026, 10, 9, 16, 30,
                        tzinfo=timezone.utc,
                    ),
                )
            )
            session.commit()

        with Session(engine) as session:
            result = list_system_daily_check_bi_pending(
                _actor(),
                date_from=date(2026, 10, 9),
                date_to=date(2026, 10, 9),
                now=datetime(
                    2026, 10, 9, 17, 0,
                    tzinfo=timezone.utc,
                ),
                session=session,
            )

        assert result["total"] == 1
        assert result["items"] == [{
            "sucursal_id": 11,
            "sucursal": "BETA",
            "business_date": "2026-10-09",
            "postpone_count": 2,
            "mandatory": True,
            "next_prompt_at": "2026-10-09T16:30:00+00:00",
            "mandatory_from_at": "2026-10-09T16:30:00+00:00",
        }]
    finally:
        engine.dispose()
