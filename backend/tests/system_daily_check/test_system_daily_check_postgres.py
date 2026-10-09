from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy.orm import Session

from app.models.system_daily_check import (
    SystemDailyCheckORM,
    SystemDailyCheckPromptStateORM,
)
from app.services.system_daily_check_service import (
    QUESTIONS,
    SystemDailyCheckConflictError,
    postpone_today,
    submit_today,
)


URL = os.getenv("SYSTEM_DAILY_CHECK_TEST_POSTGRES_URL")
MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
REVISION = "c1d5e9a7b204"


def _assert_safe_url(url: str) -> None:
    parsed = sa.engine.make_url(url)
    if (
        parsed.get_backend_name() != "postgresql"
        or parsed.database != "system_daily_check_m1_test"
        or parsed.host not in ("127.0.0.1", "localhost")
        or parsed.username != "m1_test"
    ):
        pytest.fail("Refuse non-isolated PostgreSQL URL")


def _revision():
    return ScriptDirectory(str(MIGRATIONS)).get_revision(REVISION)


def _actor(*, user_id: int = 1, branch_id: int = 10):
    return SimpleNamespace(
        id=user_id,
        username="SISTEMAS",
        rol="SISTEMAS",
        sucursal_id=branch_id,
        sucursales_ids=[],
    )


def _payload():
    return {
        "answers": [
            {
                "question_key": question.key,
                "answer": "YES",
            }
            for question in QUESTIONS
        ],
        "general_status": "NORMAL",
    }


def _apply_migration(connection, monkeypatch):
    revision = _revision()
    monkeypatch.setattr(
        revision.module,
        "op",
        Operations(MigrationContext.configure(connection)),
    )
    revision.module.upgrade()
    return revision


@pytest.mark.skipif(
    not URL,
    reason="Needs dedicated isolated PostgreSQL CI database",
)
def test_real_postgres_migration_and_concurrency(monkeypatch):
    _assert_safe_url(URL)
    engine = sa.create_engine(
        URL,
        pool_pre_ping=True,
        future=True,
    )

    base_metadata = sa.MetaData()
    users = sa.Table(
        "users",
        base_metadata,
        sa.Column("id", sa.Integer, primary_key=True),
    )
    branches = sa.Table(
        "sucursales",
        base_metadata,
        sa.Column("sucursal_id", sa.Integer, primary_key=True),
    )

    revision = None
    try:
        with engine.begin() as connection:
            base_metadata.create_all(connection)
            connection.execute(
                users.insert(),
                [{"id": 1}, {"id": 2}],
            )
            connection.execute(
                branches.insert(),
                [{"sucursal_id": 10}, {"sucursal_id": 11}],
            )
            revision = _apply_migration(connection, monkeypatch)

            inspector = sa.inspect(connection)
            assert inspector.has_table("system_daily_checks")
            assert inspector.has_table("system_daily_check_answers")
            assert inspector.has_table("system_daily_check_issues")
            assert inspector.has_table("system_daily_check_prompt_states")

        first_barrier = Barrier(2)
        t0 = datetime(
            2026,
            10,
            9,
            16,
            0,
            tzinfo=timezone.utc,
        )

        def first_postpone_worker():
            with Session(engine) as session:
                first_barrier.wait()
                try:
                    result = postpone_today(
                        _actor(),
                        now=t0,
                        session=session,
                    )
                    session.commit()
                    return ("ok", result["postpone_count"])
                except SystemDailyCheckConflictError as exc:
                    session.rollback()
                    return ("conflict", str(exc))

        with ThreadPoolExecutor(max_workers=2) as pool:
            first_results = list(
                pool.map(
                    lambda _: first_postpone_worker(),
                    range(2),
                )
            )

        assert sorted(result[0] for result in first_results) == [
            "conflict",
            "ok",
        ]
        assert [result[1] for result in first_results if result[0] == "ok"] == [1]

        with Session(engine) as session:
            state = session.execute(
                sa.select(SystemDailyCheckPromptStateORM).where(
                    SystemDailyCheckPromptStateORM.sucursal_id == 10,
                )
            ).scalar_one()
            assert state.postpone_count == 1

        second_barrier = Barrier(2)
        t1 = t0 + timedelta(minutes=5)

        def second_postpone_worker():
            with Session(engine) as session:
                second_barrier.wait()
                try:
                    result = postpone_today(
                        _actor(),
                        now=t1,
                        session=session,
                    )
                    session.commit()
                    return ("ok", result["postpone_count"])
                except SystemDailyCheckConflictError as exc:
                    session.rollback()
                    return ("conflict", str(exc))

        with ThreadPoolExecutor(max_workers=2) as pool:
            second_results = list(
                pool.map(
                    lambda _: second_postpone_worker(),
                    range(2),
                )
            )

        assert sorted(result[0] for result in second_results) == [
            "conflict",
            "ok",
        ]
        assert [result[1] for result in second_results if result[0] == "ok"] == [2]

        with Session(engine) as session:
            state = session.execute(
                sa.select(SystemDailyCheckPromptStateORM).where(
                    SystemDailyCheckPromptStateORM.sucursal_id == 10,
                )
            ).scalar_one()
            assert state.postpone_count == 2

        submit_barrier = Barrier(2)
        payload = _payload()

        def submit_worker():
            with Session(engine) as session:
                submit_barrier.wait()
                try:
                    row = submit_today(
                        _actor(user_id=2, branch_id=11),
                        payload,
                        requested_branch_id=11,
                        now=t0,
                        session=session,
                    )
                    session.commit()
                    return ("ok", row.id)
                except SystemDailyCheckConflictError as exc:
                    session.rollback()
                    return ("conflict", str(exc))

        with ThreadPoolExecutor(max_workers=2) as pool:
            submit_results = list(
                pool.map(
                    lambda _: submit_worker(),
                    range(2),
                )
            )

        assert sorted(result[0] for result in submit_results) == [
            "conflict",
            "ok",
        ]

        with Session(engine) as session:
            checks = list(
                session.scalars(
                    sa.select(SystemDailyCheckORM).where(
                        SystemDailyCheckORM.sucursal_id == 11,
                    )
                ).all()
            )
            assert len(checks) == 1
            assert checks[0].performed_by_user_id == 2

        with engine.begin() as connection:
            monkeypatch.setattr(
                revision.module,
                "op",
                Operations(MigrationContext.configure(connection)),
            )
            revision.module.downgrade()

            inspector = sa.inspect(connection)
            assert not inspector.has_table("system_daily_check_prompt_states")
            assert not inspector.has_table("system_daily_check_issues")
            assert not inspector.has_table("system_daily_check_answers")
            assert not inspector.has_table("system_daily_checks")

            base_metadata.drop_all(connection)
    finally:
        engine.dispose()
