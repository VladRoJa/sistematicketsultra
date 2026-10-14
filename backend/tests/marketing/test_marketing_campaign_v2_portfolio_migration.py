"""B1 isolated PostgreSQL migration proof; no access to production tables."""
import importlib.util
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


@pytest.mark.skipif(
    not os.getenv("PORTFOLIO_TEST_POSTGRES_URL"),
    reason="Isolated PostgreSQL URL not provided",
)
def test_b1_portfolio_migration_constraints_and_guarded_downgrade():
    path = Path(__file__).parents[2] / "migrations/versions/b856port1014_portfolio_reference_catalog.py"
    spec = importlib.util.spec_from_file_location("migration_b856port1014", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    engine = sa.create_engine(os.environ["PORTFOLIO_TEST_POSTGRES_URL"])
    table = "marketing_campaign_v2_portfolio_references"
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE IF NOT EXISTS users (id integer PRIMARY KEY)"))
        conn.execute(sa.text("INSERT INTO users (id) VALUES (7) ON CONFLICT DO NOTHING"))
        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade()
        conn.execute(sa.text(
            f"INSERT INTO {table} (business_id, display_name, app_id, source_reference, created_by_user_id) "
            "VALUES (:bid, :display, :app, :src, :actor)"
        ), dict(bid="629679279215746", display=None, app=None, src="operador", actor=7))
        row = conn.execute(sa.text(f"SELECT business_id FROM {table}")).scalar_one()
        assert row == "629679279215746"
        with pytest.raises(sa.exc.IntegrityError):
            with conn.begin_nested():
                conn.execute(sa.text(
                    f"INSERT INTO {table} (business_id, source_reference, created_by_user_id) "
                    "VALUES ('act_invalid', 'operator', 7)"
                ))
        with pytest.raises(RuntimeError, match="auditadas"):
            with Operations.context(MigrationContext.configure(conn)):
                module.downgrade()
        conn.execute(sa.text(f"DELETE FROM {table}"))
        with Operations.context(MigrationContext.configure(conn)):
            module.downgrade()
        conn.execute(sa.text("DELETE FROM users WHERE id = 7"))
    engine.dispose()
