"""B2 isolated Postgres migration: constraints, one head, no destructive rollback."""
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
REV = "c856map1014"


def test_b2_revision_linear():
    scripts = ScriptDirectory(str(MIGRATIONS))
    assert len(scripts.get_heads()) == 1  # B2 may have later linear child revisions
    assert scripts.get_revision(REV).down_revision == "b856port1014"


def test_b2_real_postgres_constraints(monkeypatch):
    raw = os.getenv("PORTFOLIO_TEST_POSTGRES_URL")
    if not raw:
        pytest.skip("Isolated portfolio_ci PostgreSQL required")
    url = sa.engine.make_url(raw)
    if (url.get_backend_name() != "postgresql"
        or url.username != "portfolio_ci"
        or url.database != "portfolio_ci"
        or url.host not in {"localhost", "127.0.0.1"}):
        pytest.fail("Never run migration test outside portfolio_ci")
    engine = sa.create_engine(raw)
    module = ScriptDirectory(str(MIGRATIONS)).get_revision(REV).module
    metadata = sa.MetaData()
    sa.Table("users", metadata, sa.Column("id", sa.Integer, primary_key=True))
    table = "marketing_campaign_v2_channel_portfolio_evidence"
    with engine.begin() as connection:
        metadata.create_all(connection)
        monkeypatch.setattr(module, "op", Operations(MigrationContext.configure(connection)))
        module.upgrade()
        connection.execute(sa.text("INSERT INTO users (id) VALUES (7)"))
        connection.execute(sa.text(
            f"INSERT INTO {table} (provider_channel_id, business_id, waba_id, state, "
            "evidence_kind, source_reference, created_by_user_id) VALUES "
            "('channel-1', '629679279215746', NULL, 'DECLARED', 'OPERATOR_STATEMENT', 'doc-1', 7)"
        ))
        connection.execute(sa.text(
            f"INSERT INTO {table} (provider_channel_id, business_id, waba_id, state, "
            "evidence_kind, source_reference, created_by_user_id) VALUES "
            "('channel-1', NULL, NULL, 'WITHDRAWN', 'OPERATOR_STATEMENT', 'doc-2', 7)"
        ))
        assert connection.scalar(sa.text(f"SELECT COUNT(*) FROM {table}")) == 2
        with connection.begin_nested() as savepoint:
            with pytest.raises(sa.exc.IntegrityError):
                connection.execute(sa.text(
                    f"INSERT INTO {table} (provider_channel_id, business_id, waba_id, state, "
                    "evidence_kind, source_reference, created_by_user_id) VALUES "
                    "('channel-bad', NULL, NULL, 'DECLARED', 'OPERATOR_STATEMENT', 'doc', 7)"
                ))
            savepoint.rollback()
        with pytest.raises(RuntimeError, match="evidencia auditada"):
            module.downgrade()
        connection.execute(sa.text(f"DELETE FROM {table}"))
        module.downgrade()
        metadata.drop_all(connection)
    engine.dispose()
