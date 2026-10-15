"""Migration gate: legacy MXN approvals stay valid and USD rows have one currency.

Runs only with a synthetic PostgreSQL database quota_ci; no prod connections.
"""
import os
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

REV = "a856usd1015"
MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"


def test_migration_is_linear():
    scripts = ScriptDirectory(str(MIGRATIONS))
    assert scripts.get_revision(REV).down_revision == "f6roster1014"
    assert len(scripts.get_heads()) == 1


def test_isolated_pg_keeps_mxn_and_forbids_mixed_or_empty_approvals(monkeypatch):
    raw = os.getenv("QUOTA_TEST_POSTGRES_URL")
    if not raw:
        pytest.skip("Only synthetic quota_ci allowed")
    parsed = sa.engine.make_url(raw)
    assert parsed.get_backend_name() == "postgresql"
    assert parsed.username == "quota_ci" and parsed.database == "quota_ci"
    assert parsed.host in {"localhost", "127.0.0.1"}

    engine = sa.create_engine(raw)
    scripts = ScriptDirectory(str(MIGRATIONS))
    upgrade = scripts.get_revision(REV).module
    with engine.begin() as conn:
        table = sa.Table(
            "marketing_campaign_v2_dispatch_approvals", sa.MetaData(),
            sa.Column("id", sa.BigInteger, primary_key=True),
            sa.Column("approved_estimated_mxn", sa.Numeric(14, 2), nullable=False),
        )
        table.create(conn)
        conn.execute(sa.text(
            "INSERT INTO marketing_campaign_v2_dispatch_approvals (id, approved_estimated_mxn) "
            "VALUES (1, 2.00)"
        ))
        monkeypatch.setattr(upgrade, "op", Operations(MigrationContext.configure(conn)))
        upgrade.upgrade()
        assert conn.scalar(sa.text(
            "SELECT approved_estimated_mxn FROM marketing_campaign_v2_dispatch_approvals WHERE id=1"
        )) == Decimal("2.00")
        conn.execute(sa.text(
            "INSERT INTO marketing_campaign_v2_dispatch_approvals "
            "(id, approved_estimated_usd) VALUES (2, 0.0542)"
        ))
        for stmt in (
            "INSERT INTO marketing_campaign_v2_dispatch_approvals "
            "(id, approved_estimated_mxn, approved_estimated_usd) VALUES (3, 0.03, 0.0542)",
            "INSERT INTO marketing_campaign_v2_dispatch_approvals (id) VALUES (4)",
        ):
            with conn.begin_nested():
                with pytest.raises(sa.exc.IntegrityError):
                    conn.execute(sa.text(stmt))
        with pytest.raises(RuntimeError, match="USD approvals"):
            upgrade.downgrade()
        conn.execute(sa.text(
            "DELETE FROM marketing_campaign_v2_dispatch_approvals WHERE id=2"
        ))
        upgrade.downgrade()
        assert conn.scalar(sa.text(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name='marketing_campaign_v2_dispatch_approvals' "
            "AND column_name='approved_estimated_usd'"
        )) == 0
    engine.dispose()
