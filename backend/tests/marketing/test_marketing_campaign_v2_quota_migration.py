"""Synthetic PostgreSQL 16 validation for quota evidence migration."""
from io import StringIO
from pathlib import Path
import os

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
REVISION = "f4d856a1b20c"
URL = os.getenv("QUOTA_TEST_POSTGRES_URL")


def module():
    return ScriptDirectory(str(MIGRATIONS)).get_revision(REVISION).module


def test_linear_ancestry_and_schema_only(monkeypatch):
    assert ScriptDirectory(str(MIGRATIONS)).get_revision(REVISION).down_revision == "e4b856c9170d"
    out = StringIO()
    ctx = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": out},
    )
    rev = module()
    monkeypatch.setattr(rev, "op", Operations(ctx))
    rev.upgrade()
    sql = out.getvalue()
    assert "marketing_campaign_v2_quota_policy_revisions" in sql
    assert "marketing_campaign_v2_quota_capacity_attestations" in sql
    assert "observed_at < expires_at" in sql
    assert "UPDATE marketing_campaign_v2" not in sql


@pytest.mark.skipif(not URL, reason="isolated synthetic PostgreSQL is required")
def test_real_postgres_constraints_and_downgrade_guards(monkeypatch):
    parsed = sa.engine.make_url(URL)
    if (parsed.get_backend_name() != "postgresql"
        or parsed.username != "quota_ci"
        or parsed.database != "quota_ci"
        or parsed.host not in {"127.0.0.1", "localhost"}):
        pytest.fail("Refusing database other than isolated quota_ci")
    engine = sa.create_engine(URL)
    rev = module()
    md = sa.MetaData()
    users = sa.Table("users", md, sa.Column("id",sa.Integer,primary_key=True))
    with engine.begin() as c:
        md.create_all(c)
        c.execute(users.insert().values(id=7))
        monkeypatch.setattr(rev,"op",Operations(MigrationContext.configure(c)))
        rev.upgrade()
        c.execute(sa.text("""
            INSERT INTO marketing_campaign_v2_quota_policy_revisions
            (provider_channel_id, portfolio_key, account_key, phone_alias,
             reset_timezone, valid_from, source_reference, created_by_user_id)
            VALUES ('channel-test','shared','account','phone','America/Tijuana',
                    now(), 'synthetic', 7)
        """))
        with c.begin_nested() as save:
            with pytest.raises(sa.exc.IntegrityError):
                c.execute(sa.text("""
                    INSERT INTO marketing_campaign_v2_quota_capacity_attestations
                    (scope_kind, scope_key, observed_at, expires_at,
                     window_ends_at, remaining_messages, source_reference, created_by_user_id)
                    VALUES ('PORTFOLIO','shared',now(),now() - interval '1 hour',
                            now() + interval '1 day', 10, 'synthetic', 7)
                """))
            save.rollback()
        with pytest.raises(RuntimeError, match="historial"):
            rev.downgrade()
        c.execute(sa.text("DELETE FROM marketing_campaign_v2_quota_policy_revisions"))
        rev.downgrade()
        md.drop_all(c)
    engine.dispose()
