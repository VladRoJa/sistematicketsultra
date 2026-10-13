"""D3c2 real PostgreSQL 16: cloned recipient/evidence and intent commit together.

Synthetic quota_ci only. No HTTP/provider call or production connection.
"""
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from pathlib import Path

from app.models.marketing import (
    MarketingCampaignV2ORM as Campaign,
    MarketingCampaignV2RecipientORM as Recipient,
    MarketingCampaignV2RecipientEvidenceORM as Evidence,
    MarketingCampaignV2ProviderCampaignORM as Child,
    MarketingCampaignV2DispatchApprovalORM as Approval,
    MarketingCampaignV2HeldReleaseIntentORM as Intent,
)
from app.services import marketing_campaign_v2_held_derived_cohort_service as svc

NOW = datetime(2026, 10, 13, 20, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[2] / "migrations"


def engine_only():
    url = os.getenv("QUOTA_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("synthetic quota_ci only")
    u = sa.engine.make_url(url)
    if (u.get_backend_name() != "postgresql" or u.username != "quota_ci"
            or u.database != "quota_ci" or u.host not in {"localhost","127.0.0.1"}):
        pytest.fail("Non-synthetic DB prohibited")
    return sa.create_engine(url)


def synthetic_schema():
    md = sa.MetaData()
    mapped = [Campaign, Recipient, Evidence, Child, Approval]
    names = {model.__table__.name for model in mapped}
    for model in mapped:
        model.__table__.to_metadata(md)
    for model in mapped:
        for column in model.__table__.columns:
            for fk in column.foreign_keys:
                target = fk.column
                table_name = target.table.name
                if table_name not in names and table_name not in md.tables:
                    sa.Table(table_name, md,
                             sa.Column(target.name, target.type, primary_key=True))
    return md, names


def test_real_postgres_freeze_clones_and_records_one_authorized_intent(monkeypatch):
    engine = engine_only()
    md, names = synthetic_schema()
    revisions = ScriptDirectory(str(ROOT))
    d1 = revisions.get_revision("d856d3c01013").module
    d2 = revisions.get_revision("e856d3c21013").module
    md.create_all(engine)
    try:
        with engine.begin() as conn:
            for migration in (d1, d2):
                monkeypatch.setattr(
                    migration, "op", Operations(MigrationContext.configure(conn)),
                )
                migration.upgrade()
        with Session(engine) as session:
            # FK stubs are strictly synthetic, not production rows.
            for table_name, pk in [
                ("users",7),("sucursales",1),
                ("marketing_campaign_v2_templates",2),
                ("marketing_campaign_v2_channel_bindings",101),
            ]:
                table = md.tables[table_name]
                field = next(iter(table.primary_key.columns)).name
                session.execute(table.insert().values({field:pk}))
            campaign = Campaign(
                id=77, name="Original", purpose="REACTIVATION", source="EXPIRED",
                audience_definition_json={"filters":{"allowed_sucursal_keys":None}},
                created_by_user_id=7, frozen_at=NOW-timedelta(hours=2),
            )
            recipient = Recipient(
                id=501, campaign_id=77, source="EXPIRED",
                phone_mx10="6861234567", sucursal="Sucursal B",
                audience_family="MES",
            )
            evidence = Evidence(
                recipient=recipient, evidence_order=0, source="EXPIRED",
                phone_mx10="6861234567", evidence_json=["synthetic-evidence"],
            )
            approval = Approval(
                id=9, campaign_v2_id=77, template_id=2,
                dispatch_fingerprint="a"*64, recipient_count=1,
                approved_estimated_mxn="0.50",
                manifest_json={"version":"D2B_READY_HELD_V1","send_authorized":False},
                approved_by_user_id=7, approved_at=NOW-timedelta(hours=1),
                expires_at=NOW+timedelta(minutes=5),
            )
            child = Child(
                id=100, campaign_v2_id=77, provider="IVENTAS",
                sucursal_id=1, sucursal_canon="B",
                channel_binding_id=101, provider_channel_id="synthetic",
                template_id=2, template_name="synthetic",
                recipient_count=1, dispatch_fingerprint="a"*64,
                idempotency_key="c"*64, status="HELD",
                hold_reason="CHANNEL_DAILY_QUOTA",
                held_by_user_id=7, held_at=NOW-timedelta(minutes=15),
                hold_evidence_json={"source":"synthetic"},
                request_snapshot_json={"leads":[{"phone":"5216861234567"}]},
                created_by_user_id=7, created_at=NOW-timedelta(minutes=15),
            )
            intent = Intent(
                id=55, source_campaign_id=77, source_approval_id=9,
                source_child_id=100, source_manifest_digest="b"*64,
                candidate_fingerprint="a"*64, candidate_recipients=1,
                evidence_json={"version":"D3C1_INTENT","send_authorized":False},
                source_reference="synthetic quota", reason="fresh window",
                requested_by_user_id=7, requested_at=NOW,
                status="PENDING_FRESH_COHORT",
            )
            session.add_all([campaign, recipient, evidence, approval, child, intent])
            session.commit()

            fresh = {
                "candidate_fingerprint":"a"*64, "recipient_count":1,
                "source_manifest_digest":"b"*64,"source_approval_id":9,
            }
            plan = NS(batches=(NS(
                sucursal_canon="B",
                recipients=(NS(recipient_id=501,phone_mx10="6861234567"),),
            ),))
            with patch.object(svc, "_evaluate", return_value=fresh), \
                 patch.object(svc, "build_campaign_v2_preflight",
                              return_value=plan), \
                 patch.object(svc, "assert_no_prior_or_pending_contact"):
                result = svc.freeze_derived_held_cohort(
                    source_campaign_id=77, source_child_id=100,
                    intent_id=55, expected_candidate_fingerprint="a"*64,
                    expected_recipient_count=1, actor_user_id=7,
                    allowed_sucursal_keys=None, session=session, now=NOW,
                )
                did = result["derived_campaign_id"]
                assert did != 77
                assert result["provider_calls"] == 0
                assert session.get(Intent, 55).derived_campaign_id == did
                assert session.get(Child, 100).status == "HELD"
                copied = session.query(Recipient).filter(
                    Recipient.campaign_id == did,
                ).all()
                assert len(copied) == 1
                assert copied[0].phone_mx10 == "6861234567"
                assert len(copied[0].evidence_rows) == 1
                assert copied[0].evidence_rows[0].evidence_json == ["synthetic-evidence"]
                assert session.query(Approval).count() == 1
                assert session.query(Child).count() == 1
                with pytest.raises(svc.HeldReleaseConflict, match="materializada"):
                    svc.freeze_derived_held_cohort(
                        source_campaign_id=77, source_child_id=100,
                        intent_id=55, expected_candidate_fingerprint="a"*64,
                        expected_recipient_count=1, actor_user_id=7,
                        allowed_sucursal_keys=None, session=session, now=NOW,
                    )
    finally:
        with engine.begin() as conn:
            conn.execute(sa.text(
                "DELETE FROM marketing_campaign_v2_held_release_intents"
            ))
            # An existing derived cohort is real historical data; only isolated
            # test rows can be explicitly cleaned before reversible migration.
            d2.downgrade()
            d1.downgrade()
        md.drop_all(engine)
        engine.dispose()
