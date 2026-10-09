from __future__ import annotations

import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory


URL = os.getenv("SYSTEM_DAILY_CHECK_TEST_POSTGRES_URL")
MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
M1_REVISION = "c1d5e9a7b204"
M3_REVISION = "d4a7c91e2b55"


def _assert_safe_url(url: str) -> None:
    parsed = sa.engine.make_url(url)
    if (
        parsed.get_backend_name() != "postgresql"
        or parsed.database != "system_daily_check_m1_test"
        or parsed.host not in ("127.0.0.1", "localhost")
        or parsed.username != "m1_test"
    ):
        pytest.fail("Refuse non-isolated PostgreSQL URL")


def _revision(revision_id: str):
    return ScriptDirectory(str(MIGRATIONS)).get_revision(
        revision_id
    )


@pytest.mark.skipif(
    not URL,
    reason="Needs dedicated isolated PostgreSQL CI database",
)
def test_m3_rollout_migration_on_real_postgres(monkeypatch):
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

    m1 = _revision(M1_REVISION)
    m3 = _revision(M3_REVISION)

    try:
        with engine.begin() as connection:
            base_metadata.create_all(connection)

            monkeypatch.setattr(
                m1.module,
                "op",
                Operations(
                    MigrationContext.configure(connection)
                ),
            )
            m1.module.upgrade()

            monkeypatch.setattr(
                m3.module,
                "op",
                Operations(
                    MigrationContext.configure(connection)
                ),
            )
            m3.module.upgrade()

            inspector = sa.inspect(connection)
            assert inspector.has_table(
                "system_daily_check_rollout_branches"
            )

            columns = {
                column["name"]
                for column in inspector.get_columns(
                    "system_daily_check_rollout_branches"
                )
            }
            assert {
                "id",
                "sucursal_id",
                "enabled_from",
                "disabled_from",
                "configured_by_user_id",
                "disabled_by_user_id",
                "created_at",
                "updated_at",
            } <= columns

            indexes = {
                index["name"]
                for index in inspector.get_indexes(
                    "system_daily_check_rollout_branches"
                )
            }
            assert (
                "ix_system_daily_check_rollout_effective_dates"
                in indexes
            )
            assert (
                "ix_system_daily_check_rollout_branch_dates"
                in indexes
            )

            fk_targets = {
                fk["referred_table"]
                for fk in inspector.get_foreign_keys(
                    "system_daily_check_rollout_branches"
                )
            }
            assert fk_targets == {"users", "sucursales"}

            monkeypatch.setattr(
                m3.module,
                "op",
                Operations(
                    MigrationContext.configure(connection)
                ),
            )
            m3.module.downgrade()
            inspector = sa.inspect(connection)
            assert not inspector.has_table(
                "system_daily_check_rollout_branches"
            )

            monkeypatch.setattr(
                m1.module,
                "op",
                Operations(
                    MigrationContext.configure(connection)
                ),
            )
            m1.module.downgrade()
            base_metadata.drop_all(connection)
    finally:
        engine.dispose()
