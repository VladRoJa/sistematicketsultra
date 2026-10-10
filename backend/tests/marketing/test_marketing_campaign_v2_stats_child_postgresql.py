"""PostgreSQL integration acceptance for child snapshot link migration.

Run only with an isolated database (M3_TEST_POSTGRES_URL). No production DSN
should be passed to this test. The transaction is rolled back after assertions.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

REVISION = "f4a2b6c8d0e1"
MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
URL = os.environ.get("M3_TEST_POSTGRES_URL")


@pytest.mark.skipif(not URL, reason="Requires dedicated isolated PostgreSQL test DSN")
def test_child_snapshot_upgrade_and_downgrade_on_postgresql():
    # Deliberately do not use Flask app's configured database. Fail closed
    # even if an operator accidentally passes a production URL.
    parsed = sa.engine.make_url(URL)
    if (parsed.database != "m3_child_snapshots"
            or parsed.host not in {"127.0.0.1", "localhost"}
            or parsed.username != "m3_test"):
        pytest.fail("Refusing to run destructive migration QA outside isolated m3_child_snapshots DB")
    engine = sa.create_engine(URL, pool_pre_ping=True)
    if engine.dialect.name != "postgresql":
        engine.dispose()
        pytest.fail("M3 integration test requires PostgreSQL")

    metadata = sa.MetaData()
    parent = sa.Table(
        "marketing_campaign_v2_campaigns", metadata,
        sa.Column("id", sa.BigInteger, primary_key=True),
    )
    child = sa.Table(
        "marketing_campaign_v2_provider_campaigns", metadata,
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("campaign_v2_id", sa.BigInteger, nullable=False),
    )
    snapshot = sa.Table(
        "marketing_campaign_v2_provider_stats_snapshots", metadata,
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("campaign_v2_id", sa.BigInteger, nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("provider_campaign_id", sa.String(255), nullable=False),
    )
    revision = ScriptDirectory(str(MIGRATIONS)).get_revision(REVISION)

    # All DDL and DML live within one transaction; close implies rollback.
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            metadata.create_all(connection, checkfirst=False)
            connection.execute(parent.insert(), [{"id": 7}])
            connection.execute(child.insert(), [
                {"id": 101, "campaign_v2_id": 7},
                {"id": 102, "campaign_v2_id": 7},
            ])
            connection.execute(snapshot.insert(), [
                {"id": 201, "campaign_v2_id": 7, "provider": "IVENTAS",
                 "provider_campaign_id": "legacy-provider"},
            ])

            context = MigrationContext.configure(connection)
            migration_op = Operations(context)
            original_op = revision.module.op
            revision.module.op = migration_op
            try:
                revision.module.upgrade()
                columns = sa.inspect(connection).get_columns(snapshot.name)
                new_column = next(
                    value for value in columns
                    if value["name"] == "provider_campaign_child_id"
                )
                assert new_column["nullable"] is True

                # Historical snapshot retains its data and is unlinked.
                old = connection.execute(sa.text(
                    "SELECT provider_campaign_id, provider_campaign_child_id "
                    "FROM marketing_campaign_v2_provider_stats_snapshots "
                    "WHERE id = 201"
                )).one()
                assert old == ("legacy-provider", None)

                connection.execute(sa.text(
                    "UPDATE marketing_campaign_v2_provider_stats_snapshots "
                    "SET provider_campaign_child_id = 101 WHERE id = 201"
                ))
                assert connection.execute(sa.text(
                    "SELECT provider_campaign_child_id "
                    "FROM marketing_campaign_v2_provider_stats_snapshots "
                    "WHERE id = 201"
                )).scalar_one() == 101

                # Reject nonexistent child IDs and preserve the transaction.
                with connection.begin_nested() as nested:
                    with pytest.raises(sa.exc.IntegrityError):
                        connection.execute(sa.text(
                            "UPDATE marketing_campaign_v2_provider_stats_snapshots "
                            "SET provider_campaign_child_id = 999999 WHERE id = 201"
                        ))
                    nested.rollback()

                connection.execute(sa.text(
                    "DELETE FROM marketing_campaign_v2_provider_campaigns "
                    "WHERE id = 101"
                ))
                assert connection.execute(sa.text(
                    "SELECT provider_campaign_child_id "
                    "FROM marketing_campaign_v2_provider_stats_snapshots "
                    "WHERE id = 201"
                )).scalar_one() is None

                indexes = sa.inspect(connection).get_indexes(snapshot.name)
                assert any(
                    index["name"] == "ix_mkt_v2_stats_provider_campaign_child"
                    for index in indexes
                )
                revision.module.downgrade()
                assert "provider_campaign_child_id" not in {
                    col["name"]
                    for col in sa.inspect(connection).get_columns(snapshot.name)
                }
                assert connection.execute(sa.text(
                    "SELECT provider_campaign_id "
                    "FROM marketing_campaign_v2_provider_stats_snapshots "
                    "WHERE id = 201"
                )).scalar_one() == "legacy-provider"
            finally:
                revision.module.op = original_op
        finally:
            transaction.rollback()
    engine.dispose()


def test_refuses_non_isolated_database_before_creating_engine(monkeypatch):
    import sys
    module = sys.modules[__name__]
    monkeypatch.setattr(
        module, "URL",
        "postgresql+psycopg2://postgres:password@prod.example.com:5432/production",
    )
    with pytest.raises(pytest.fail.Exception, match="Refusing to run"):
        test_child_snapshot_upgrade_and_downgrade_on_postgresql()
