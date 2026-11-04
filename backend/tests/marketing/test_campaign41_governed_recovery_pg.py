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
    session.add(Execution(
        id=41, approval_id=9, manifest_digest=DIGEST,
        confirmed_by_user_id=7, confirmed_at=NOW + timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=10),
        status="REVIEW_REQUIRED", last_child_id=255, updated_at=NOW,
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



def test_governed_recovery_commits_before_provider_and_blocks_replay(monkeypatch):
    engine = _engine()
    metadata = _schema()
    metadata.create_all(engine)
    try:
        with Session(engine) as session:
            _seed(session)
            original_get = Session.get

            def get_entity(self, entity, ident, *args, **kwargs):
                if entity is UserORM:
                    return NS(id=int(ident))
                return original_get(self, entity, ident, *args, **kwargs)

            monkeypatch.setattr(Session, "get", get_entity)
            monkeypatch.setattr(
                svc, "resolve_marketing_access",
                lambda actor: NS(is_global=True, can_send_campaigns=True,
                                 can_manage_dispatch_config=True),
            )
            batches = tuple(NS(
                sucursal_canon=f"TEST_{child_id}",
                sucursal_id=1, channel_binding_id=101,
                provider_channel_id="synthetic-channel", template_id=2,
                template_name="synthetic-template", recipients=(child_id,),
            ) for child_id in (253, 255, 256, 257))
            plan = NS(campaign_id=41, mode="IMMEDIATE", provider="IVENTAS",
                      ready=True, dispatch_fingerprint=FINGERPRINT,
                      batches=batches)
            manifest = {batch.sucursal_canon: {"planned_status": "READY"}
                        for batch in batches}
            review = NS(
                approval_id=9, execution_id=41, digest=DIGEST,
                quota_basis="SUITE_BRANCH_EXCEPTION_CAPS_V1",
                accepted_original=((253, "original-253"),),
                plan_review=NS(
                    plan=plan, ready_children=(
                        NS(child_id=256, batch=batches[2]),
                        NS(child_id=257, batch=batches[3]),
                    ),
                ),
            )
            monkeypatch.setattr(
                svc, "build_campaign_v2_preflight", lambda **_: plan)
            monkeypatch.setattr(
                svc, "budget_for_existing_approval", lambda **_: {})
            monkeypatch.setattr(
                svc, "_assert_manifest", lambda *args: manifest)
            monkeypatch.setattr(
                svc, "build_provider_campaign_idempotency_key",
                lambda *, batch, **_: f"{int(batch.sucursal_canon.rsplit('_', 1)[1]):064x}")
            monkeypatch.setattr(
                svc, "build_campaign_v2_provider_dispatch_batch",
                lambda **_: NS())
            monkeypatch.setattr(
                svc, "serialize_campaign_v2_provider_request_snapshot",
                lambda _outbound: {"synthetic": True})
            monkeypatch.setattr(
                svc, "_assess_scopes",
                lambda *args, **kwargs: (
                    {"status": "REVIEWABLE"},
                    {("CHANNEL", "synthetic-channel"): 1},
                    {("CHANNEL", "synthetic-channel"): None},
                    {},
                ),
            )
            admissions = []
            monkeypatch.setattr(
                svc, "verify_outbound_contact_admission",
                lambda *, child, session: admissions.append(child.id),
            )
            class Provider:
                calls = 0
                def create_campaign(self, _dispatch):
                    self.calls += 1
                    child_id = (256 if self.calls == 1 else 257)
                    # A second connection proves the transaction was already
                    # committed before the provider callback begins.
                    with engine.connect() as other:
                        status = other.scalar(sa.text(
                            "SELECT status FROM marketing_campaign_v2_provider_campaigns "
                            "WHERE id = :id"), {"id": child_id})
                        old = other.scalar(sa.text(
                            "SELECT status FROM marketing_campaign_v2_provider_campaigns "
                            "WHERE id = 255"))
                        state = other.scalar(sa.text(
                            "SELECT status FROM marketing_campaign_v2_governed_executions "
                            "WHERE id = 41"))
                    assert (status, old, state) == (
                        "SUBMITTING", "PROVIDER_ERROR", "REVIEW_REQUIRED")
                    return NS(
                        provider_campaign_id=f"synthetic-accepted-{child_id}",
                        deduplicated=False, response_metadata={},
                        http_status=200,
                    )
            provider = Provider()
            first = svc.send_next(
                review=review, child=review.plan_review.ready_children[0],
                actor_user_id=7, completed=(), session=session, provider=provider,
            )
            assert first == ("TEST_256", "SUBMITTED", "synthetic-accepted-256")
            assert session.get(Child, 256).status == "SUBMITTED"

            # Replaying the same child after one acceptance cannot POST.
            with pytest.raises(svc.GovernedRecoveryBlocked):
                svc.send_next(
                    review=review, child=review.plan_review.ready_children[0],
                    actor_user_id=7, completed=(), session=session, provider=provider,
                )
            assert provider.calls == 1

            second = svc.send_next(
                review=review, child=review.plan_review.ready_children[1],
                actor_user_id=7, completed=((256, "synthetic-accepted-256"),),
                session=session, provider=provider,
            )
            assert second == ("TEST_257", "SUBMITTED", "synthetic-accepted-257")
            assert provider.calls == 2
            assert admissions == [256, 257]
            assert session.get(Child, 255).status == "PROVIDER_ERROR"
            assert session.get(Child, 253).provider_campaign_id == "original-253"
            assert session.get(Execution, 41).status == "REVIEW_REQUIRED"
            assert session.get(BackgroundJob, 5).status == "REVIEW_REQUIRED"
    finally:
        metadata.drop_all(engine)
        engine.dispose()
