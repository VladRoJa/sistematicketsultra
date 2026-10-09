from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, create_engine
from sqlalchemy.orm import Session

from app.models import (
    Sucursal,
    SystemDailyCheckRolloutBranchORM,
)
from app.services.system_daily_check_bi_service import (
    configure_system_daily_check_rollout_today,
    resolve_system_daily_check_branch_universe,
)
from app.services.system_daily_check_service import (
    SystemDailyCheckAuthorizationError,
    SystemDailyCheckValidationError,
    list_system_daily_check_branches,
)
from app.utils.scope_utils import CORPORATE_BRANCH_ID, ROOT_BRANCH_ID
from app.utils.sucursal_audience import TECHNICAL_SUCURSAL_IDS


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

    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        metadata.create_all(connection)
        connection.exec_driver_sql("INSERT INTO users (id) VALUES (1)")

        rows = [
            (
                10,
                "A10",
                "ACTIVA A",
                "BC",
                "ACTIVA",
                0,
            ),
            (
                11,
                "A11",
                "ACTIVA B",
                "BC",
                "ACTIVA",
                0,
            ),
            (
                12,
                "C12",
                "CERRADA",
                "BC",
                "CERRADA",
                0,
            ),
            (
                13,
                "D13",
                "DEMO",
                "BC",
                "ACTIVA",
                1,
            ),
        ]
        for (
            branch_id,
            serie,
            name,
            estado,
            operational_status,
            is_demo,
        ) in rows:
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
                VALUES (?, ?, ?, ?, ?, ?, 'MEXICALI', 'N/A')
                """,
                (
                    branch_id,
                    serie,
                    name,
                    estado,
                    operational_status,
                    is_demo,
                ),
            )

        for technical_id in sorted(TECHNICAL_SUCURSAL_IDS):
            if technical_id in {10, 11, 12, 13}:
                continue
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
                VALUES (?, 'TECH', 'TECNICA', 'BC', 'ACTIVA', 0, 'N/A', 'N/A')
                """,
                (technical_id,),
            )

    return engine


def test_rollout_universe_separates_potential_from_expected():
    engine = _engine()
    try:
        with Session(engine) as session:
            session.add_all(
                [
                    SystemDailyCheckRolloutBranchORM(
                        sucursal_id=10,
                        enabled_from=date(2026, 10, 9),
                        disabled_from=None,
                        configured_by_user_id=1,
                    ),
                    SystemDailyCheckRolloutBranchORM(
                        sucursal_id=11,
                        enabled_from=date(2026, 10, 10),
                        disabled_from=None,
                        configured_by_user_id=1,
                    ),
                    SystemDailyCheckRolloutBranchORM(
                        sucursal_id=13,
                        enabled_from=date(2026, 10, 9),
                        disabled_from=None,
                        configured_by_user_id=1,
                    ),
                ]
            )
            session.commit()

        with Session(engine) as session:
            day_one = resolve_system_daily_check_branch_universe(
                as_of_date=date(2026, 10, 9),
                session=session,
            )
            assert {
                row["sucursal_id"]
                for row in day_one["potential_branches"]
            } == {10, 11, CORPORATE_BRANCH_ID}
            assert {
                row["sucursal_id"]
                for row in day_one["expected_branches"]
            } == {10}
            assert day_one["potential_count"] == 3
            assert day_one["expected_count"] == 1

            day_two = resolve_system_daily_check_branch_universe(
                as_of_date=date(2026, 10, 10),
                session=session,
            )
            assert {
                row["sucursal_id"]
                for row in day_two["expected_branches"]
            } == {10, 11}
            assert day_two["expected_count"] == 2
    finally:
        engine.dispose()


def test_rollout_universe_rejects_non_date_cutoff():
    engine = _engine()
    try:
        with Session(engine) as session:
            try:
                resolve_system_daily_check_branch_universe(
                    as_of_date="2026-10-09",
                    session=session,
                )
            except ValueError as exc:
                assert "datetime.date" in str(exc)
            else:
                raise AssertionError("Debe rechazar as_of_date no date.")
    finally:
        engine.dispose()


def _actor(
    *,
    role="SISTEMAS",
    username="sistemas-user",
    branch_id=ROOT_BRANCH_ID,
):
    return SimpleNamespace(
        id=1,
        rol=role,
        username=username,
        sucursal_id=branch_id,
    )


def test_configure_rollout_today_replaces_forward_without_rewriting_history():
    engine = _engine()
    now = datetime(2026, 10, 9, 16, 0, tzinfo=timezone.utc)
    try:
        with Session(engine) as session:
            session.add(
                SystemDailyCheckRolloutBranchORM(
                    sucursal_id=10,
                    enabled_from=date(2026, 10, 8),
                    disabled_from=None,
                    configured_by_user_id=1,
                )
            )
            session.commit()

        with Session(engine) as session:
            result = configure_system_daily_check_rollout_today(
                _actor(),
                branch_ids=[11],
                now=now,
                session=session,
            )
            session.commit()
            assert {
                row["sucursal_id"]
                for row in result["expected_branches"]
            } == {11}

        with Session(engine) as session:
            rows = list(
                session.query(SystemDailyCheckRolloutBranchORM)
                .order_by(
                    SystemDailyCheckRolloutBranchORM.sucursal_id.asc()
                )
                .all()
            )
            assert len(rows) == 2
            assert rows[0].sucursal_id == 10
            assert rows[0].enabled_from == date(2026, 10, 8)
            assert rows[0].disabled_from == date(2026, 10, 8)
            assert rows[0].disabled_by_user_id == 1
            assert rows[1].sucursal_id == 11
            assert rows[1].enabled_from == date(2026, 10, 9)
            assert rows[1].disabled_from is None

            prior = resolve_system_daily_check_branch_universe(
                as_of_date=date(2026, 10, 8),
                session=session,
            )
            assert {
                row["sucursal_id"]
                for row in prior["expected_branches"]
            } == {10}
    finally:
        engine.dispose()


def test_checklist_branch_catalog_canonicalizes_root_to_corporate():
    engine = _engine()
    try:
        with Session(engine) as session:
            catalog = list_system_daily_check_branches(
                _actor(branch_id=ROOT_BRANCH_ID),
                session=session,
            )
            branch_ids = {
                row["sucursal_id"]
                for row in catalog["branches"]
            }
            assert CORPORATE_BRANCH_ID in branch_ids
            assert ROOT_BRANCH_ID not in branch_ids
            assert (
                catalog["preferred_branch_id"]
                == CORPORATE_BRANCH_ID
            )
    finally:
        engine.dispose()


def test_corporate_is_selectable_but_root_remains_excluded():
    engine = _engine()
    now = datetime(2026, 10, 9, 16, 0, tzinfo=timezone.utc)
    try:
        with Session(engine) as session:
            result = configure_system_daily_check_rollout_today(
                _actor(),
                branch_ids=[CORPORATE_BRANCH_ID],
                now=now,
                session=session,
            )
            session.commit()
            assert {
                row["sucursal_id"]
                for row in result["expected_branches"]
            } == {CORPORATE_BRANCH_ID}

        with Session(engine) as session:
            with pytest.raises(
                SystemDailyCheckValidationError,
                match="técnica no seleccionable",
            ):
                configure_system_daily_check_rollout_today(
                    _actor(),
                    branch_ids=[ROOT_BRANCH_ID],
                    now=now,
                    session=session,
                )
    finally:
        engine.dispose()


def test_configure_rollout_rejects_non_mvp_actor():
    engine = _engine()
    try:
        with Session(engine) as session:
            with pytest.raises(SystemDailyCheckAuthorizationError):
                configure_system_daily_check_rollout_today(
                    _actor(role="GERENTE", username="gerente.demo"),
                    branch_ids=[10],
                    now=datetime(
                        2026,
                        10,
                        9,
                        16,
                        0,
                        tzinfo=timezone.utc,
                    ),
                    session=session,
                )
    finally:
        engine.dispose()
