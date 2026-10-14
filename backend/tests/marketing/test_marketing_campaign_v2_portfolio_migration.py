"""Issue 856 B1: isolated PostgreSQL 16 migration, never production."""
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
REV = "b856port1014"


def test_b1_migration_is_linear_and_append_only():
    module = ScriptDirectory(str(MIGRATIONS)).get_revision(REV).module
    assert module.down_revision == "f856opcap1013"


def test_b1_migration_postgres_constraints_and_downgrade(monkeypatch):
    raw = os.getenv("PORTFOLIO_TEST_POSTGRES_URL")
    if not raw:
        pytest.skip("isolated PostgreSQL 16 portfolio_ci required")
    uri = sa.engine.make_url(raw)
    if (
        uri.get_backend_name() != "postgresql"
        or uri.username != "portfolio_ci"
        or uri.database != "portfolio_ci"
        or uri.host not in {"127.0.0.1", "localhost"}
    ):
        pytest.fail("Refusing PostgreSQL outside isolated portfolio_ci")

    module = ScriptDirectory(str(MIGRATIONS)).get_revision(REV).module
    engine = sa.create_engine(raw)
    metadata = sa.MetaData()
    sa.Table("users", metadata, sa.Column("id", sa.Integer, primary_key=True))
    table = "marketing_campaign_v2_portfolio_references"

    with engine.begin() as conn:
        metadata.create_all(conn)
        monkeypatch.setattr(module, "op", Operations(MigrationContext.configure(conn)))
        module.upgrade()
        conn.execute(sa.text("INSERT INTO users (id) VALUES (7)"))
        conn.execute(sa.text(
            f"INSERT INTO {table} (business_id, display_name, app_id, source_reference, created_by_user_id) "
            "VALUES (:bid, NULL, NULL, :src, :actor)"
        ), dict(bid="629679279215746", src="operator evidence", actor=7))
        assert conn.scalar(sa.text(f"SELECT business_id FROM {table}")) == "629679279215746"
        with conn.begin_nested() as save:
            with pytest.raises(sa.exc.IntegrityError):
                conn.execute(sa.text(
                    f"INSERT INTO {table} (business_id, source_reference, created_by_user_id) "
                    "VALUES ('act_invalid', 'operator', 7)"
                ))
            save.rollback()
        with pytest.raises(RuntimeError, match="auditadas"):
            module.downgrade()
        conn.execute(sa.text(f"DELETE FROM {table}"))
        module.downgrade()
        metadata.drop_all(conn)
    engine.dispose()
