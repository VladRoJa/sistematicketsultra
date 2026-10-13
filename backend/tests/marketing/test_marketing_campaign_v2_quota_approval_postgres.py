"""Isolated PostgreSQL 16 D2a migration, constraints and transaction lock tests."""
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

URL = os.getenv("QUOTA_TEST_POSTGRES_URL")
MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"


def safe_engine():
    if not URL:
        pytest.skip("isolated quota_ci PostgreSQL 16 required")
    parsed = sa.engine.make_url(URL)
    if (parsed.get_backend_name() != "postgresql" or
            parsed.username != "quota_ci" or
            parsed.database != "quota_ci" or
            parsed.host not in {"127.0.0.1", "localhost"}):
        pytest.fail("Refusing database other than isolated quota_ci")
    return sa.create_engine(URL)


def test_postgres_advisory_lock_serializes_portfolio():
    engine = safe_engine()
    key = "mkt_v2_quota:PORTFOLIO:shared"
    with engine.connect() as a, engine.connect() as b:
        ta = a.begin()
        tb = b.begin()
        try:
            a.execute(sa.text(
                "SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"
            ), {"scope": key})
            assert b.scalar(sa.text(
                "SELECT pg_try_advisory_xact_lock(hashtextextended(:scope, 0))"
            ), {"scope": key}) is False
            ta.commit()
            assert b.scalar(sa.text(
                "SELECT pg_try_advisory_xact_lock(hashtextextended(:scope, 0))"
            ), {"scope": key}) is True
        finally:
            if ta.is_active:
                ta.rollback()
            if tb.is_active:
                tb.rollback()
    engine.dispose()


def test_postgres_reservation_schema_and_downgrade(monkeypatch):
    engine = safe_engine()
    md = sa.MetaData()
    sa.Table("users", md, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table("marketing_campaign_v2_campaigns", md,
             sa.Column("id", sa.BigInteger, primary_key=True))
    sa.Table("marketing_campaign_v2_templates", md,
             sa.Column("id", sa.BigInteger, primary_key=True))
    scripts = ScriptDirectory(str(MIGRATIONS))
    prior = scripts.get_revision("f4d856a1b20c").module
    d2 = scripts.get_revision("a856d2a01013").module
    with engine.begin() as c:
        md.create_all(c)
        monkeypatch.setattr(prior, "op", Operations(MigrationContext.configure(c)))
        monkeypatch.setattr(d2, "op", Operations(MigrationContext.configure(c)))
        prior.upgrade()
        d2.upgrade()
        c.execute(sa.text("INSERT INTO users (id) VALUES (7)"))
        c.execute(sa.text("INSERT INTO marketing_campaign_v2_campaigns (id) VALUES (99)"))
        c.execute(sa.text("INSERT INTO marketing_campaign_v2_templates (id) VALUES (2)"))
        attestation = c.scalar(sa.text("""
            INSERT INTO marketing_campaign_v2_quota_capacity_attestations
            (scope_kind,scope_key,observed_at,expires_at,window_ends_at,
             remaining_messages,source_reference,created_by_user_id)
            VALUES ('PORTFOLIO','shared',now()-interval '1 minute',
                    now()+interval '30 minutes',now()+interval '1 hour',
                    12,'synthetic operator evidence',7)
            RETURNING id
        """))
        approval_id = c.scalar(sa.text("""
            INSERT INTO marketing_campaign_v2_dispatch_approvals
            (campaign_v2_id,template_id,dispatch_fingerprint,recipient_count,
             approved_estimated_mxn,manifest_json,approved_by_user_id,approved_at,expires_at)
            VALUES (99,2,:fingerprint,12,3.60,'{}'::json,7,now(),
                    now()+interval '12 minutes') RETURNING id
        """), {"fingerprint": "a" * 64})
        c.execute(sa.text("""
            INSERT INTO marketing_campaign_v2_capacity_reservations
            (approval_id,attestation_id,scope_kind,scope_key,reserved_messages,reserved_until)
            VALUES (:approval,:attestation,'PORTFOLIO','shared',12,now()+interval '12 minutes')
        """), {"approval": approval_id, "attestation": attestation})
        with c.begin_nested() as sp:
            with pytest.raises(sa.exc.IntegrityError):
                c.execute(sa.text("""
                    INSERT INTO marketing_campaign_v2_capacity_reservations
                    (approval_id,attestation_id,scope_kind,scope_key,reserved_messages,reserved_until)
                    VALUES (:a,:b,'PORTFOLIO','shared',1,now()+interval '12 minutes')
                """), {"a": approval_id, "b": attestation})
            sp.rollback()
        with pytest.raises(RuntimeError, match="historial"):
            d2.downgrade()
        c.execute(sa.text("DELETE FROM marketing_campaign_v2_capacity_reservations"))
        c.execute(sa.text("DELETE FROM marketing_campaign_v2_dispatch_approvals"))
        d2.downgrade()
        c.execute(sa.text("DELETE FROM marketing_campaign_v2_quota_capacity_attestations"))
        prior.downgrade()
        md.drop_all(c)
    engine.dispose()
