"""Issue 856 operator caps migration: PostgreSQL 16 only, no production access."""
from io import StringIO
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
REV = "f856opcap1013"


def test_operator_cap_revision_is_linear_and_data_preserving(monkeypatch):
    migration = ScriptDirectory(str(MIGRATIONS)).get_revision(REV)
    assert migration.down_revision == "c13a70e4d82c"
    out = StringIO()
    ctx = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": out},
    )
    monkeypatch.setattr(migration.module, "op", Operations(ctx))
    migration.module.upgrade()
    sql = out.getvalue()
    assert "operational_channel_cap" in sql
    assert "operational_portfolio_cap" in sql
    assert "attestation_id" in sql
    assert "DELETE FROM" not in sql and "UPDATE " not in sql


def test_postgres_legacy_and_operator_reservations_coexist(monkeypatch):
    raw = os.getenv("QUOTA_TEST_POSTGRES_URL")
    if not raw:
        pytest.skip("isolated synthetic quota_ci required")
    uri = sa.engine.make_url(raw)
    if (uri.get_backend_name() != "postgresql" or
            uri.username != "quota_ci" or uri.database != "quota_ci" or
            uri.host not in {"127.0.0.1", "localhost"}):
        pytest.fail("Refusing database other than isolated quota_ci")
    engine = sa.create_engine(raw)
    md = sa.MetaData()
    sa.Table("users", md, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table("marketing_campaign_v2_campaigns", md, sa.Column("id", sa.BigInteger, primary_key=True))
    sa.Table("marketing_campaign_v2_templates", md, sa.Column("id", sa.BigInteger, primary_key=True))
    scripts = ScriptDirectory(str(MIGRATIONS))
    base = scripts.get_revision("f4d856a1b20c").module
    approval = scripts.get_revision("a856d2a01013").module
    new = scripts.get_revision(REV).module
    with engine.begin() as conn:
        md.create_all(conn)
        for mod in (base, approval, new):
            monkeypatch.setattr(mod, "op", Operations(MigrationContext.configure(conn)))
        base.upgrade()
        approval.upgrade()
        conn.execute(sa.text("INSERT INTO users (id) VALUES (7)"))
        conn.execute(sa.text("INSERT INTO marketing_campaign_v2_campaigns (id) VALUES (99)"))
        conn.execute(sa.text("INSERT INTO marketing_campaign_v2_templates (id) VALUES (2)"))
        attestation = conn.scalar(sa.text("""
            INSERT INTO marketing_campaign_v2_quota_capacity_attestations
            (scope_kind,scope_key,observed_at,expires_at,window_ends_at,
             remaining_messages,source_reference,created_by_user_id)
            VALUES ('CHANNEL','old',now()-interval '1 minute',
                    now()+interval '30 minutes',now()+interval '1 hour',9,'old proof',7)
            RETURNING id
        """))
        old_approval = conn.scalar(sa.text("""
            INSERT INTO marketing_campaign_v2_dispatch_approvals
            (campaign_v2_id,template_id,dispatch_fingerprint,recipient_count,
             approved_estimated_mxn,manifest_json,approved_by_user_id,approved_at,expires_at)
            VALUES (99,2,:fp,1,1.00,'{}'::json,7,now(),now()+interval '10 minutes')
            RETURNING id
        """), {"fp": "a" * 64})
        conn.execute(sa.text("""
            INSERT INTO marketing_campaign_v2_capacity_reservations
            (approval_id,attestation_id,scope_kind,scope_key,reserved_messages,reserved_until)
            VALUES (:a,:b,'CHANNEL','old',1,now()+interval '10 minutes')
        """), {"a": old_approval, "b": attestation})
        new.upgrade()
        assert conn.scalar(sa.text("""
            SELECT attestation_id FROM marketing_campaign_v2_capacity_reservations
            WHERE scope_key='old'
        """)) == attestation
        conn.execute(sa.text("""
            INSERT INTO marketing_campaign_v2_quota_policy_revisions
            (provider_channel_id,portfolio_key,account_key,phone_alias,
             nominal_channel_limit,operational_channel_cap,operational_portfolio_cap,
             reset_timezone,valid_from,source_reference,created_by_user_id)
            VALUES ('channel1','shared','a','phone',100000,500,1000,
                    'America/Tijuana',now(),'operator test',7)
        """))
        with conn.begin_nested() as save:
            with pytest.raises(sa.exc.IntegrityError):
                conn.execute(sa.text("""
                    INSERT INTO marketing_campaign_v2_quota_policy_revisions
                    (provider_channel_id,portfolio_key,account_key,phone_alias,
                     operational_channel_cap,reset_timezone,valid_from,
                     source_reference,created_by_user_id)
                    VALUES ('channel2','shared','a','phone',3,
                            'America/Tijuana',now(),'bad partial',7)
                """))
            save.rollback()
        # Existing schema permits one reservation per scope per approval.
        conn.execute(sa.text("""
            INSERT INTO marketing_campaign_v2_capacity_reservations
            (approval_id,attestation_id,scope_kind,scope_key,reserved_messages,reserved_until)
            VALUES (:a,NULL,'PORTFOLIO','shared',1,now()+interval '10 minutes')
        """), {"a": old_approval})
        with pytest.raises(RuntimeError, match="configuración operativa"):
            new.downgrade()
        conn.execute(sa.text("DELETE FROM marketing_campaign_v2_capacity_reservations WHERE scope_key='shared'"))
        conn.execute(sa.text("DELETE FROM marketing_campaign_v2_quota_policy_revisions"))
        new.downgrade()
        conn.execute(sa.text("DELETE FROM marketing_campaign_v2_capacity_reservations"))
        conn.execute(sa.text("DELETE FROM marketing_campaign_v2_dispatch_approvals"))
        conn.execute(sa.text("DELETE FROM marketing_campaign_v2_quota_capacity_attestations"))
        approval.downgrade()
        base.downgrade()
        md.drop_all(conn)
    engine.dispose()
