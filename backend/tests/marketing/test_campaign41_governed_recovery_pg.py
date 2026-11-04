"""PostgreSQL-only integration: one-off governed continuation commits before HTTP.

All data are synthetic and restricted to the disposable quota_ci database.
No iVentas API key or network provider is ever used.
"""
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.marketing import (
    MarketingCampaignV2ORM as Campaign,
    MarketingCampaignV2ProviderCampaignORM as Child,
    MarketingCampaignV2DispatchApprovalORM as Approval,
    MarketingCampaignV2GovernedExecutionORM as Execution,
)
from app.models.marketing_campaign_v2_background_job import (
    MarketingCampaignV2BackgroundJobORM as BackgroundJob,
)
from app.models.user_model import UserORM
from app.services import marketing_campaign_v2_governed_recovery_service as svc

NOW = datetime(2026, 11, 3, 23, 30, tzinfo=timezone.utc)
FINGERPRINT = "b" * 64
KEY = "c" * 64
MANIFEST = {"version": "D2B_READY_HELD_V1", "test": "synthetic"}
DIGEST = hashlib.sha256(
    json.dumps(MANIFEST, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    .encode("utf-8")
).hexdigest()


def _engine():
    url = os.getenv("QUOTA_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("No synthetic PostgreSQL quota_ci configured")
    parsed = sa.engine.make_url(url)
    if (parsed.get_backend_name() != "postgresql"
            or parsed.host not in {"localhost", "127.0.0.1"}
            or parsed.database != "quota_ci" or parsed.username != "quota_ci"):
        pytest.fail("Refusing any database other than localhost quota_ci")
    return sa.create_engine(url)


def _schema():
    metadata = sa.MetaData()
    for model in (Campaign, Child, Approval, Execution, BackgroundJob):
        model.__table__.to_metadata(metadata)
    known = set(metadata.tables)
    for model in (Campaign, Child, Approval, Execution, BackgroundJob):
        for column in model.__table__.columns:
            for foreign_key in column.foreign_keys:
                other = foreign_key.column
                if other.table.name not in known:
                    sa.Table(other.table.name, metadata,
                             sa.Column(other.name, other.type, primary_key=True))
                    known.add(other.table.name)
    return metadata


def _seed(session):
    session.execute(sa.text("INSERT INTO users (id) VALUES (7)"))
    session.execute(sa.text("INSERT INTO sucursales (sucursal_id) VALUES (1)"))
    session.execute(sa.text(
        "INSERT INTO marketing_campaign_v2_channel_bindings (id) VALUES (101)"))
    session.execute(sa.text(
        "INSERT INTO marketing_campaign_v2_templates (id) VALUES (2)"))
    session.add(Campaign(
        id=41, name="Synthetic campaign 41", purpose="NEW_SALE",
        source="EXPIRED", audience_definition_json={}, created_by_user_id=7,
    ))
    session.flush()
    session.add(Approval(
        id=9, campaign_v2_id=41, template_id=2,
        dispatch_fingerprint=FINGERPRINT, recipient_count=4,
        approved_estimated_usd=0, manifest_json=MANIFEST,
        approved_by_user_id=7, approved_at=NOW,
        expires_at=NOW + timedelta(minutes=10), revision_no=1,
    ))
    session.flush()
    session.add(Execution(
        id=41, approval_id=9, manifest_digest=DIGEST,
        confirmed_by_user_id=7, confirmed_at=NOW + timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=10),
        status="REVIEW_REQUIRED", last_child_id=255, updated_at=NOW,
    ))
    for child_id, status, provider_id in [
        (253, "SUBMITTED", "original-253"),
        (255, "PROVIDER_ERROR", None),
        (256, "READY", None),
        (257, "READY", None),
    ]:
        session.add(Child(
            id=child_id, campaign_v2_id=41, provider="IVENTAS",
            sucursal_id=1, sucursal_canon=f"TEST_{child_id}",
            channel_binding_id=101, provider_channel_id="synthetic-channel",
            template_id=2, template_name="synthetic-template",
            recipient_count=1, dispatch_fingerprint=FINGERPRINT,
            idempotency_key=f"{child_id:064x}", status=status,
            request_snapshot_json={"synthetic": True},
            provider_response_json=(
                {"http_status": 400} if child_id == 255 else {}),
            provider_campaign_id=provider_id,
            error_code="TEMPLATE_NOT_FOUND" if child_id == 255 else None,
            support_ref="bc-mw1c1why-phq041" if child_id == 255 else None,
            submit_started_at=NOW + timedelta(minutes=2) if status != "READY" else None,
            submitted_at=NOW + timedelta(minutes=3) if status == "SUBMITTED" else None,
            submitted_by_user_id=7 if status == "SUBMITTED" else None,
            created_by_user_id=7, created_at=NOW, updated_at=NOW,
        ))
    session.flush()
    session.add(BackgroundJob(
        id=5, campaign_v2_id=41, approval_id=9, execution_id=41,
        operator_user_id=7, request_key="a" * 64, manifest_digest=DIGEST,
        pending_child_ids=[255, 256, 257], pending_children_digest="d" * 64,
        initial_pending_count=3, status="REVIEW_REQUIRED",
        start_deadline_at=NOW + timedelta(minutes=10),
        current_child_id=255, last_accepted_child_id=253,
        created_at=NOW, updated_at=NOW,
    ))
    session.commit()
