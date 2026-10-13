"""SEC-856-QA-01: PostgreSQL 16 interleaving of HELD freeze vs V2 claim.

Two real SQLAlchemy sessions, same advisory lock, separate connections.
No HTTP, no provider, and only the synthetic quota_ci local database.
"""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from datetime import datetime, timezone
import os
import time

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.marketing import (
    MarketingCampaignV2ORM as Campaign,
    MarketingCampaignV2RecipientORM as Recipient,
    MarketingCampaignV2ProviderCampaignORM as Child,
)
from app.services.marketing_campaign_v2_contact_gate_service import (
    CampaignV2ContactGateConflict, acquire_campaign_v2_contact_gate,
    verify_outbound_contact_admission,
)
from app.services.marketing_campaign_v2_derived_contact_guard import (
    DERIVED_SOURCE, DerivedContactConflict, assert_no_prior_or_pending_contact,
)

PHONE = "6861234567"


def _engine():
    raw = os.getenv("QUOTA_TEST_POSTGRES_URL")
    if not raw:
        pytest.skip("isolated quota_ci required")
    parts = sa.engine.make_url(raw)
    if (parts.get_backend_name() != "postgresql" or
            parts.username != "quota_ci" or parts.database != "quota_ci" or
            parts.host not in {"localhost", "127.0.0.1"}):
        pytest.fail("Refusing any production or unknown database")
    return sa.create_engine(raw, pool_size=3, max_overflow=0)


def _schema():
    md = sa.MetaData()
    mapped = (Campaign, Recipient, Child)
    names = {m.__table__.name for m in mapped}
    for model in mapped:
        model.__table__.to_metadata(md)
    for model in mapped:
        for col in model.__table__.columns:
            for fk in col.foreign_keys:
                parent = fk.column
                if parent.table.name not in names and parent.table.name not in md.tables:
                    sa.Table(parent.table.name, md, sa.Column(
                        parent.name, parent.type, primary_key=True,
                    ))
    return md


@pytest.mark.parametrize("winner", ["send", "freeze"])
def test_real_two_connection_interleaving_denies_other_claim(winner):
    engine = _engine()
    md = _schema()
    md.create_all(engine)
    try:
        with Session(engine) as setup:
            for table_name, value in [
                ("users", 7), ("sucursales", 1),
                ("marketing_campaign_v2_templates", 2),
                ("marketing_campaign_v2_channel_bindings", 101),
            ]:
                table = md.tables[table_name]
                pk = next(iter(table.primary_key.columns)).name
                setup.execute(table.insert().values({pk: value}))
            setup.add_all([
                Campaign(
                    id=77, name="Original", purpose="REACTIVATION",
                    source="EXPIRED", audience_definition_json={},
                    created_by_user_id=7,
                ),
                Campaign(
                    id=88, name="Derived", purpose="REACTIVATION",
                    source=DERIVED_SOURCE, audience_definition_json={},
                    created_by_user_id=7,
                ),
            ])
            setup.flush()
            setup.add(Child(
                id=100, campaign_v2_id=77, provider="IVENTAS",
                sucursal_id=1, sucursal_canon="A",
                channel_binding_id=101, provider_channel_id="synthetic",
                template_id=2, template_name="synthetic",
                recipient_count=1, dispatch_fingerprint="a"*64,
                idempotency_key="b"*64, status="READY",
                request_snapshot_json={
                    "provider_channel_id": "synthetic",
                    "leads": [{"phone": "521" + PHONE}],
                },
                created_by_user_id=7,
            ))
            setup.commit()

        started = Event()

        def other_action():
            with Session(engine) as other:
                started.set()
                # MUST wait for main transaction's common gate.
                acquire_campaign_v2_contact_gate(other)
                if winner == "send":
                    with pytest.raises(DerivedContactConflict, match="coincidente"):
                        assert_no_prior_or_pending_contact(
                            phones=(PHONE,), session=other,
                        )
                else:
                    with pytest.raises(CampaignV2ContactGateConflict, match="reservado"):
                        verify_outbound_contact_admission(
                            child=other.get(Child, 100), session=other,
                        )
                other.rollback()
                return "rejected"

        with Session(engine) as first:
            acquire_campaign_v2_contact_gate(first)
            if winner == "send":
                child = first.get(Child, 100)
                verify_outbound_contact_admission(child=child, session=first)
                child.status = "SUBMITTING"
            else:
                first.add(Recipient(
                    campaign_id=88, phone_mx10=PHONE, source="EXPIRED",
                    sucursal="Synthetic",
                ))
            first.flush()
            with ThreadPoolExecutor(max_workers=1) as pool:
                later = pool.submit(other_action)
                assert started.wait(timeout=5), "second transaction did not start"
                # Confirm no independent admission while the first lock is open.
                time.sleep(0.1)
                assert not later.done()
                first.commit()
                assert later.result(timeout=10) == "rejected"

        with Session(engine) as verify:
            child = verify.get(Child, 100)
            recipient_count = verify.query(Recipient).filter(
                Recipient.campaign_id == 88,
            ).count()
            assert (child.status, recipient_count) == (
                ("SUBMITTING", 0) if winner == "send" else ("READY", 1)
            )
    finally:
        md.drop_all(engine)
        engine.dispose()
