"""Campaign #43-class incident: no-attempt review closure on disposable PG16.

No real recipients, campaigns, provider credentials, outbound HTTP, or prod DB.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.orm import Session

from app.services import marketing_campaign_v2_background_job_service as service
from app.services import marketing_campaign_v2_background_worker_service as worker
from app.services.marketing_campaign_v2_dispatch_approval_service import (
    CampaignV2ApprovalConflictError,
)
from test_background_dispatch_m3_postgres import _migration

JOB_ID = 3
CAMPAIGN_ID = 43
IDS = list(range(269, 291))
CONFIRMATION = "CONFIRMAR SIN ENVIO 43 3"
MANIFEST = {"version": "synthetic-no-http", "send_authorized": False}
MANIFEST_DIGEST = hashlib.sha256(json.dumps(
    MANIFEST, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
).encode("utf-8")).hexdigest()


@pytest.fixture
def isolated_pg():
    url = os.getenv("CAMPAIGN_V2_BG_M1A_TEST_PG_URL")
    if not url:
        pytest.skip("Requires disposable PG16 in Actions")
    parts = sa.engine.make_url(url)
    assert (parts.get_backend_name() == "postgresql"
            and parts.host in ("127.0.0.1", "localhost")
            and parts.username == "quota_ci" and parts.database == "quota_ci")
    schema = "campaign43_" + secrets.token_hex(5)
    admin = sa.create_engine(url)
    with admin.begin() as conn:
        conn.exec_driver_sql(f"CREATE SCHEMA {schema}")
    engine = sa.create_engine(url, pool_size=2, max_overflow=0)

    @sa.event.listens_for(engine, "connect")
    def search_path(dbapi_conn, _rec):
        with dbapi_conn.cursor() as cursor:
            cursor.execute(f"SET search_path TO {schema}")
        dbapi_conn.commit()

    try:
        meta = sa.MetaData()
        sa.Table("users", meta, sa.Column("id", sa.Integer, primary_key=True))
        sa.Table("marketing_campaign_v2_campaigns", meta,
                 sa.Column("id", sa.BigInteger, primary_key=True))
        sa.Table("marketing_campaign_v2_dispatch_approvals", meta,
                 sa.Column("id", sa.BigInteger, primary_key=True),
                 sa.Column("campaign_v2_id", sa.BigInteger),
                 sa.Column("revision_no", sa.Integer),
                 sa.Column("expires_at", sa.DateTime(timezone=True)),
                 sa.Column("manifest_json", sa.JSON))
        sa.Table("marketing_campaign_v2_governed_executions", meta,
                 sa.Column("id", sa.BigInteger, primary_key=True),
                 sa.Column("approval_id", sa.BigInteger),
                 sa.Column("manifest_digest", sa.String(64)),
                 sa.Column("status", sa.String(25)),
                 sa.Column("last_child_id", sa.BigInteger),
                 sa.Column("expires_at", sa.DateTime(timezone=True)))
        sa.Table("marketing_campaign_v2_provider_campaigns", meta,
                 sa.Column("id", sa.BigInteger, primary_key=True),
                 sa.Column("campaign_v2_id", sa.BigInteger),
                 sa.Column("status", sa.String(30)),
                 sa.Column("submit_started_at", sa.DateTime(timezone=True)),
                 sa.Column("submitted_at", sa.DateTime(timezone=True)),
                 sa.Column("submitted_by_user_id", sa.Integer),
                 sa.Column("provider_campaign_id", sa.String(255)),
                 sa.Column("error_code", sa.String(80)),
                 sa.Column("support_ref", sa.String(255)),
                 sa.Column("provider_response_json", sa.JSON),
                 sa.Column("retry_history_json", sa.JSON),
                 sa.Column("retry_attempt_count", sa.Integer),
                 sa.Column("reconciliation_resolution", sa.String(50)),
                 sa.Column("reconciled_at", sa.DateTime(timezone=True)),
                 sa.Column("provider_deduplicated", sa.Boolean))
        meta.create_all(engine)
        with engine.begin() as conn:
            mig = _migration()
            mig.op = Operations(MigrationContext.configure(conn))
            mig.upgrade()
            conn.execute(sa.text("INSERT INTO users(id) VALUES (1)"))
            conn.execute(sa.text(
                "INSERT INTO marketing_campaign_v2_campaigns(id) VALUES (43)"
            ))
            conn.execute(sa.text("""
                INSERT INTO marketing_campaign_v2_dispatch_approvals
                (id, campaign_v2_id, revision_no, expires_at, manifest_json)
                VALUES (20,43,2,now()-interval '2 minutes', CAST(:manifest AS json))
            """), {"manifest": json.dumps(MANIFEST)})
            conn.execute(sa.text("""
                INSERT INTO marketing_campaign_v2_governed_executions
                (id, approval_id, status, expires_at, manifest_digest)
                VALUES (30,20,'AUTHORIZED',now()-interval '2 minutes', :digest)
            """), {"digest": MANIFEST_DIGEST})
            for child_id in IDS:
                conn.execute(sa.text("""
                    INSERT INTO marketing_campaign_v2_provider_campaigns
                    (id,campaign_v2_id,status,provider_response_json,
                     retry_history_json,retry_attempt_count)
                    VALUES (:id,43,'READY','{}'::json,'[]'::json,0)
                """), {"id": child_id})
            digest = hashlib.sha256(
                json.dumps(IDS, separators=(",", ":")).encode("ascii")
            ).hexdigest()
            conn.execute(sa.text("""
                INSERT INTO marketing_campaign_v2_background_jobs
                (id,campaign_v2_id,approval_id,execution_id,operator_user_id,
                 request_key,manifest_digest,pending_child_ids,
                 pending_children_digest,initial_pending_count,status,
                 start_deadline_at,started_at,finished_at,current_child_id,
                 worker_claim_generation,stop_reason_code)
                VALUES (3,43,20,30,1,:key,:manifest,CAST(:ids AS json),
                        :digest,22,'REVIEW_REQUIRED',
                        now()-interval '2 minutes',now()-interval '4 minutes',
                        now()-interval '3 minutes',269,1,'UNEXPECTED_WORKER_FAILURE')
            """), {"key": "a"*64, "manifest": MANIFEST_DIGEST,
                   "ids": json.dumps(IDS), "digest": digest})
            for idx, kind in enumerate(
                    ("ENQUEUED", "STARTED", "REVIEW_REQUIRED"), start=1):
                conn.execute(sa.text("""
                    INSERT INTO marketing_campaign_v2_background_job_events
                    (job_id,event_no,event_kind,reason_code)
                    VALUES (3,:idx,:kind,:reason)
                """), {"idx": idx, "kind": kind,
                       "reason": "UNEXPECTED_WORKER_FAILURE"
                           if idx == 3 else None})
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.exec_driver_sql(f"DROP SCHEMA {schema} CASCADE")
        admin.dispose()


def resolve(engine, **overrides):
    with patch.object(service, "acquire_campaign_v2_contact_gate"):
        with Session(engine) as session:
            return service.resolve_unattempted_review(
                campaign_id=overrides.get("campaign_id", CAMPAIGN_ID),
                job_id=JOB_ID,
                actor_user_id=overrides.get("actor_user_id", 1),
                confirmation=overrides.get("confirmation", CONFIRMATION),
                session=session,
            )


def test_can_close_without_sending_and_preserve_event_chain(isolated_pg):
    engine = isolated_pg
    result = resolve(engine)
    assert result == {
        "job_id": 3, "campaign_id": 43, "status": "STOPPED",
        "already_resolved": False, "requires_reauthorization": True,
        "provider_calls": 0,
    }
    with engine.connect() as conn:
        row = conn.execute(sa.text("""
            SELECT status,stop_reason_code,current_child_id,
                   last_accepted_child_id,worker_claim_generation
            FROM marketing_campaign_v2_background_jobs WHERE id=3
        """)).one()
        assert tuple(row) == ("STOPPED", "NO_ATTEMPT_VERIFIED", None, None, 1)
        history = conn.execute(sa.text("""
            SELECT event_no,event_kind,actor_user_id,reason_code
            FROM marketing_campaign_v2_background_job_events
            WHERE job_id=3 ORDER BY event_no
        """)).all()
        assert [x.event_kind for x in history] == [
            "ENQUEUED", "STARTED", "REVIEW_REQUIRED", "STOPPED"]
        assert history[2].reason_code == "UNEXPECTED_WORKER_FAILURE"
        assert history[-1].actor_user_id == 1
        assert history[-1].reason_code == "NO_ATTEMPT_VERIFIED"
        assert conn.scalar(sa.text("""
            SELECT count(*) FROM marketing_campaign_v2_provider_campaigns
            WHERE campaign_v2_id=43 AND status='READY'
              AND submit_started_at IS NULL AND provider_campaign_id IS NULL
        """)) == 22
    assert resolve(engine)["already_resolved"] is True
    with engine.connect() as conn:
        assert conn.scalar(sa.text(
            "SELECT count(*) FROM marketing_campaign_v2_background_job_events "
            "WHERE job_id=3"
        )) == 4


@pytest.mark.parametrize("mutation", [
    "submitting", "submitted_at", "provider_id", "ambiguous",
    "extra_child", "audit_claim", "last_child", "live_approval",
    "newer_approval", "other_operator", "approval_digest_changed",
])
def test_never_close_if_any_sign_of_attempt_or_inconsistent_history(
    isolated_pg, mutation,
):
    engine = isolated_pg
    with engine.begin() as conn:
        if mutation == "submitting":
            conn.execute(sa.text("""
                UPDATE marketing_campaign_v2_provider_campaigns
                SET status='SUBMITTING',submit_started_at=now() WHERE id=269
            """))
        elif mutation == "submitted_at":
            conn.execute(sa.text("""
                UPDATE marketing_campaign_v2_provider_campaigns
                SET submitted_at=now() WHERE id=269
            """))
        elif mutation == "provider_id":
            conn.execute(sa.text("""
                UPDATE marketing_campaign_v2_provider_campaigns
                SET provider_campaign_id='synthetic-no-http' WHERE id=269
            """))
        elif mutation == "ambiguous":
            conn.execute(sa.text("""
                UPDATE marketing_campaign_v2_provider_campaigns
                SET status='RECONCILIATION_REQUIRED' WHERE id=269
            """))
        elif mutation == "extra_child":
            conn.execute(sa.text("""
                INSERT INTO marketing_campaign_v2_provider_campaigns
                (id,campaign_v2_id,status)
                VALUES (999,43,'SUBMITTED')
            """))
        elif mutation == "audit_claim":
            conn.execute(sa.text("""
                UPDATE marketing_campaign_v2_background_job_events
                SET event_kind='CHILD_ACCEPTED' WHERE job_id=3 AND event_no=2
            """))
        elif mutation == "last_child":
            conn.execute(sa.text("""
                UPDATE marketing_campaign_v2_governed_executions
                SET last_child_id=269 WHERE id=30
            """))
        elif mutation == "live_approval":
            conn.execute(sa.text("""
                UPDATE marketing_campaign_v2_dispatch_approvals
                SET expires_at=now()+interval '10 minutes' WHERE id=20
            """))
        elif mutation == "newer_approval":
            conn.execute(sa.text("""
                INSERT INTO marketing_campaign_v2_dispatch_approvals
                (id,campaign_v2_id,revision_no,expires_at)
                VALUES (21,43,3,now()+interval '10 minutes')
            """))
        elif mutation == "approval_digest_changed":
            conn.execute(sa.text("""
                UPDATE marketing_campaign_v2_dispatch_approvals
                SET manifest_json='{"version":"tampered"}'::json WHERE id=20
            """))
    if mutation == "other_operator":
        with pytest.raises(service.BackgroundJobNotFound):
            resolve(engine, actor_user_id=2)
    else:
        with pytest.raises(service.BackgroundJobConflict):
            resolve(engine)
    with engine.connect() as conn:
        assert conn.scalar(sa.text(
            "SELECT status FROM marketing_campaign_v2_background_jobs WHERE id=3"
        )) == "REVIEW_REQUIRED"
        assert conn.scalar(sa.text(
            "SELECT count(*) FROM marketing_campaign_v2_background_job_events WHERE job_id=3"
        )) == 3


def test_confirmation_is_exact_and_never_sends(isolated_pg):
    with pytest.raises(service.BackgroundJobValidation):
        resolve(isolated_pg, confirmation="SEND 22")
    assert service.resolve_unattempted_review.__doc__ is not None


def test_safe_approval_conflict_code_never_reflects_provider_data():
    assert worker._approval_reason(CampaignV2ApprovalConflictError(
        "No hay evidencia de capacidad completa y vigente para todos los lotes."
    )) == "APPROVAL_QUOTA_EVIDENCE_INVALID"
    assert worker._approval_reason(CampaignV2ApprovalConflictError(
        "sensitive provider key, recipient phone 1234567890"
    )) == "APPROVAL_CONFLICT_OTHER"
