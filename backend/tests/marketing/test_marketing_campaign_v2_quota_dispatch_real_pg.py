"""D2c PostgreSQL 16: durable claim visible to another connection before fake provider.

No network or external API; refuses all databases except synthetic quota_ci.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest.mock import patch
import os

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.marketing import (
    MarketingCampaignV2ProviderCampaignORM as Child,
    MarketingCampaignV2GovernedExecutionORM as Execution,
)
from app.services import marketing_campaign_v2_governed_dispatch_service as svc

NOW = datetime(2026, 10, 13, 18, tzinfo=timezone.utc)
DIGEST = "a"*64


def _isolated_engine():
    url = os.getenv("QUOTA_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("isolated PostgreSQL quota_ci required")
    parts = sa.engine.make_url(url)
    if (parts.get_backend_name() != "postgresql" or
            parts.host not in {"localhost", "127.0.0.1"} or
            parts.database != "quota_ci" or parts.username != "quota_ci"):
        pytest.fail("Refusing any non-synthetic PostgreSQL database")
    return sa.create_engine(url)


def _tables():
    md = sa.MetaData()
    stub = {}
    for name, col, typ in [
        ("users", "id", sa.Integer),
        ("sucursales", "sucursal_id", sa.Integer),
        ("marketing_campaign_v2_campaigns", "id", sa.BigInteger),
        ("marketing_campaign_v2_channel_bindings", "id", sa.BigInteger),
        ("marketing_campaign_v2_templates", "id", sa.BigInteger),
        ("marketing_campaign_v2_dispatch_approvals", "id", sa.BigInteger),
    ]:
        stub[name] = sa.Table(name, md, sa.Column(col, typ, primary_key=True))
    Child.__table__.to_metadata(md)
    Execution.__table__.to_metadata(md)
    return md, stub


def test_provider_only_sees_committed_inflight_and_replay_cannot_post():
    engine = _isolated_engine()
    md, stub = _tables()
    md.create_all(engine)
    try:
        with Session(engine) as session:
            session.execute(stub["users"].insert().values(id=7))
            session.execute(stub["sucursales"].insert().values(sucursal_id=1))
            session.execute(stub["marketing_campaign_v2_campaigns"].insert().values(id=99))
            session.execute(stub["marketing_campaign_v2_channel_bindings"].insert().values(id=101))
            session.execute(stub["marketing_campaign_v2_templates"].insert().values(id=2))
            session.execute(stub["marketing_campaign_v2_dispatch_approvals"].insert().values(id=9))
            session.add(Child(
                id=100, campaign_v2_id=99, provider="IVENTAS",
                sucursal_id=1, sucursal_canon="A", channel_binding_id=101,
                provider_channel_id="synthetic-only", template_id=2,
                template_name="no-send-fixture", recipient_count=5,
                dispatch_fingerprint="b"*64, idempotency_key="c"*64,
                status="READY", request_snapshot_json={},
                provider_response_json={}, created_by_user_id=7,
                created_at=NOW, updated_at=NOW,
            ))
            session.add(Execution(
                id=41, approval_id=9, manifest_digest=DIGEST,
                confirmed_by_user_id=7, confirmed_at=NOW,
                expires_at=NOW + timedelta(minutes=10),
                status="AUTHORIZED", updated_at=NOW,
            ))
            session.commit()

            batch = NS(sucursal_canon="A", recipients=(1,2,3,4,5))
            plan = NS(campaign_id=99, batches=(batch,))
            manifest = {"A": {"planned_status": "READY"}}

            def synthetic_review(**kwargs):
                # Each HTTP-like request uses its own SQLAlchemy session.
                current_session = kwargs["session"]
                return (NS(id=9), plan, manifest, [current_session.get(Child, 100)], DIGEST)

            class SyntheticProvider:
                calls = 0

                def create_campaign(self, _dispatch):
                    self.calls += 1
                    # A separate transaction must already see both claims.
                    with engine.connect() as separate:
                        current_child = separate.scalar(sa.text(
                            "SELECT status FROM marketing_campaign_v2_provider_campaigns WHERE id=100"
                        ))
                        current_gate = separate.scalar(sa.text(
                            "SELECT status FROM marketing_campaign_v2_governed_executions WHERE id=41"
                        ))
                        claim = separate.scalar(sa.text(
                            "SELECT last_child_id FROM marketing_campaign_v2_governed_executions WHERE id=41"
                        ))
                    assert (current_child, current_gate, claim) == (
                        "SUBMITTING", "IN_FLIGHT", 100,
                    )
                    # A competing request arrives while the first request
                    # is inside the external HTTP-like provider call.
                    with Session(engine) as competing:
                        with pytest.raises(
                            svc.GovernedDispatchConflict, match="usada"
                        ):
                            svc.execute_governed_child(
                                campaign_id=99, execution_id=41, child_id=100,
                                expected_digest=DIGEST, actor_user_id=7,
                                provider=self, send_enabled=True,
                                governed_enabled=True,
                                allowed_sucursal_keys=None,
                                session=competing, now=NOW,
                            )
                    assert self.calls == 1
                    return NS(
                        provider_campaign_id="FAKE-NOT-A-REAL-ACCOUNT",
                        deduplicated=False, response_metadata={"synthetic": True},
                        http_status=200,
                    )
            provider = SyntheticProvider()
            with patch.object(svc, "_locked_review", side_effect=synthetic_review), \
                 patch.object(svc, "_check_child_identities"), \
                 patch.object(svc, "build_campaign_v2_provider_dispatch_batch",
                              return_value=NS()):
                result = svc.execute_governed_child(
                    campaign_id=99, execution_id=41, child_id=100,
                    expected_digest=DIGEST, actor_user_id=7,
                    provider=provider, send_enabled=True,
                    governed_enabled=True, allowed_sucursal_keys=None,
                    session=session, now=NOW,
                )
                assert result["status"] == "SUBMITTED"
                assert session.get(Child, 100).status == "SUBMITTED"
                assert session.get(Execution, 41).status == "COMPLETE"
                with pytest.raises(svc.GovernedDispatchConflict):
                    svc.execute_governed_child(
                        campaign_id=99, execution_id=41, child_id=100,
                        expected_digest=DIGEST, actor_user_id=7,
                        provider=provider, send_enabled=True,
                        governed_enabled=True, allowed_sucursal_keys=None,
                        session=session, now=NOW,
                    )
                assert provider.calls == 1
    finally:
        md.drop_all(engine)
        engine.dispose()
