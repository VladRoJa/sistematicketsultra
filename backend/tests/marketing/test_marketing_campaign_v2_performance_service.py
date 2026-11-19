"""M1 delivery/frequency contract against persisted children, not parent snapshots."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import BigInteger, Column, Integer, MetaData, Table, create_engine
from sqlalchemy.orm import Session

from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2ProviderCampaignORM,
    MarketingCampaignV2ProviderRecipientObservationORM,
    MarketingCampaignV2ProviderStatsSnapshotORM,
)
from app.services.marketing_campaign_v2_performance_service import (
    CampaignV2PerformanceValidationError,
    _summarize_lots,
    _window,
    build_campaign_v2_performance,
)


AT = datetime(2026, 10, 14, 18, 0, tzinfo=timezone.utc)


def _child(identifier, branch, campaign_id, provider_id, recipients=2):
    return MarketingCampaignV2ProviderCampaignORM(
        id=identifier, campaign_v2_id=campaign_id,
        provider="IVENTAS", sucursal_id=identifier,
        sucursal_canon=branch, channel_binding_id=1,
        provider_channel_id="ch-" + str(identifier),
        template_id=1, template_name="demo",
        recipient_count=recipients, status="SUBMITTED",
        dispatch_fingerprint=str(identifier % 10) * 64,
        idempotency_key=str(identifier % 10) * 64,
        provider_campaign_id=provider_id,
        submitted_at=AT,
        created_at=AT, updated_at=AT,
    )


def _snapshot(identifier, provider_id, fetched_at, successful, failed, sent, delivered, viewed):
    return MarketingCampaignV2ProviderStatsSnapshotORM(
        id=identifier, campaign_v2_id=7, provider="IVENTAS",
        provider_campaign_id=provider_id, fetched_at=fetched_at,
        analytics_status="ok", raw_successful=successful, raw_failed=failed,
        raw_sent=sent, raw_delivered=delivered, raw_viewed=viewed,
        raw_answered=0, raw_interaction_groups=0, raw_interaction_items=0,
        analytics_json=None, button_interactions_json=[],
        provider_recipient_count=successful + failed,
        matched_recipient_count=0, unmatched_provider_count=successful + failed,
        frozen_recipient_without_provider_status_count=0,
        fingerprint=str(identifier % 10) * 64, created_at=fetched_at,
    )


def _observation(sid, phone, outcome, bucket):
    return MarketingCampaignV2ProviderRecipientObservationORM(
        snapshot_id=sid, normalized_phone="mx10:" + phone,
        campaign_recipient_id=None, outcome=outcome,
        delivery_bucket=bucket, button_labels_json=[],
        created_at=AT,
    )


@pytest.fixture
def active_session():
    engine = create_engine("sqlite://")
    meta = MetaData()
    Table("users", meta, Column("id", Integer, primary_key=True))
    Table("sucursales", meta, Column("sucursal_id", Integer, primary_key=True))
    Table("marketing_campaign_v2_channel_bindings", meta,
          Column("id", BigInteger, primary_key=True))
    Table("marketing_campaign_v2_templates", meta,
          Column("id", BigInteger, primary_key=True))
    Table("marketing_campaign_v2_recipients", meta,
          Column("id", BigInteger, primary_key=True))
    for model in (
        MarketingCampaignV2ORM, MarketingCampaignV2ProviderCampaignORM,
        MarketingCampaignV2ProviderStatsSnapshotORM,
        MarketingCampaignV2ProviderRecipientObservationORM,
    ):
        model.__table__.to_metadata(meta)
    meta.create_all(engine)
    with Session(engine) as active:
        active.add(MarketingCampaignV2ORM(
            id=7, name="Multisucursal", purpose="REACTIVATION",
            source="EXPIRED_MEMBERS", provider=None, provider_campaign_id=None,
            audience_definition_json={
                "filters": {"allowed_sucursal_keys": ["AZAHARES_CUL", "SEND_CUL"]}
            }, frozen_at=AT, created_at=AT, updated_at=AT,
        ))
        active.add_all([
            _child(101, "AZAHARES_CUL", 7, "provider-a", 3),
            _child(102, "SEND_CUL", 7, "provider-b", 2),
            _child(103, "AZAHARES_CUL", 7, "provider-missing", 1),
        ])
        active.add_all([
            _snapshot(201, "provider-a", AT, 1, 0, 1, 0, 0),
            _snapshot(202, "provider-a", AT.replace(hour=20), 2, 1, 0, 1, 1),
            _snapshot(203, "provider-b", AT, 1, 1, 1, 0, 0),
        ])
        active.add_all([
            _observation(201, "6860000001", "SUCCESSFUL", "SENT"),
            _observation(202, "6860000001", "SUCCESSFUL", "DELIVERED"),
            _observation(202, "6860000002", "SUCCESSFUL", "VIEWED"),
            _observation(202, "6860000003", "FAILED", None),
            _observation(203, "6860000001", "SUCCESSFUL", "SENT"),
            _observation(203, "6860000004", "FAILED", None),
        ])
        active.commit()
        yield active
    engine.dispose()


def test_m1_latest_snapshot_per_child_frequency_and_missing_evidence(active_session):
    report = build_campaign_v2_performance(
        from_date="2026-10-01", to_date="2026-10-31",
        allowed_sucursal_keys=None, session=active_session,
    )
    assert report["campaign_count"] == 1
    assert len(report["campaigns"]) == 1
    assert report["campaigns"][0]["name"] == "Multisucursal"
    assert report["campaigns"][0]["lots"] == 3
    assert report["campaigns"][0]["successful"] == 3
    assert report["campaigns"][0]["unique_successful_phones"] == 2
    assert report["campaigns"][0]["repeated_successful_phones"] == 1
    summary = report["summary"]
    assert summary["lots"] == 3
    assert summary["lots_with_snapshot"] == 2
    assert summary["lots_without_snapshot"] == 1
    assert summary["recipient_count"] == 6
    assert summary["successful"] == 3  # 2 latest from A + 1 from B
    assert summary["failed"] == 2
    assert summary["unique_successful_phones"] == 2
    assert summary["repeated_successful_phones"] == 1
    assert report["frequency"] == {"once": 1, "twice": 1, "three": 0, "four_plus": 0}
    assert summary["estimated_delivered_usd"] == "0.1084"
    assert summary["evidence_status"] == "INCOMPLETE"
    assert [(x["sucursal_canon"], x["successful"])
            for x in report["branches"]] == [("AZAHARES_CUL", 2), ("SEND_CUL", 1)]
    assert report["cost"]["actual_billed_usd"] is None
    assert "6860000001" not in repr(report)  # no personal data in API


def test_m1_does_not_leak_multibranch_campaign_to_partial_scope(active_session):
    report = build_campaign_v2_performance(
        from_date="2026-10-01", to_date="2026-10-31",
        allowed_sucursal_keys=["AZAHARES_CUL"], session=active_session,
    )
    assert report["campaign_count"] == 0
    assert report["summary"]["lots"] == 0
    assert report["branches"] == []
    assert report["campaigns"] == []


def test_m1_period_excludes_outside_and_invalid_ranges(active_session):
    report = build_campaign_v2_performance(
        from_date="2026-11-01", to_date="2026-11-30",
        allowed_sucursal_keys=None, session=active_session,
    )
    assert report["summary"]["lots"] == 0
    assert report["frequency"]["once"] == 0
    for begin, end in [("2026-10-31", "2026-10-01"),
                       ("2026-10-01", "2026-11-01"),
                       ("bad", "2026-10-01")]:
        with pytest.raises(CampaignV2PerformanceValidationError):
            _window(begin, end)


def test_m1_indicative_cost_is_not_submitted_or_real_invoice():
    rows = [
        {"recipient_count": 100, "has_snapshot": True,
         "successful": 80, "failed": 20, "sent": 40,
         "delivered": 20, "viewed": 20, "recipient_mismatch": False},
        {"recipient_count": 20, "has_snapshot": False,
         "successful": 0, "failed": 0, "sent": 0,
         "delivered": 0, "viewed": 0, "recipient_mismatch": False},
    ]
    result = _summarize_lots(rows)
    assert result["recipient_count"] == 120
    assert result["successful"] == 80
    assert result["estimated_delivery_count"] == 40
    assert result["estimated_delivered_usd"] == "2.1680"
    assert result["evidence_status"] == "INCOMPLETE"


def test_m1_window_respects_tijuana_dst_offsets():
    _, _, start, end = _window("2026-11-01", "2026-11-01")
    assert start == datetime(2026, 11, 1, 7, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)
    assert (end - start).total_seconds() == 25 * 3600


def test_m1_cross_campaign_phones_are_global_unique_but_repeat_in_frequency(active_session):
    active_session.add(MarketingCampaignV2ORM(
        id=8, name="Segundo esfuerzo", purpose="REACTIVATION",
        source="EXPIRED_MEMBERS", provider=None, provider_campaign_id=None,
        audience_definition_json={
            "filters": {"allowed_sucursal_keys": ["AZAHARES_CUL"]}
        }, frozen_at=AT, created_at=AT, updated_at=AT,
    ))
    active_session.add(_child(104, "AZAHARES_CUL", 8, "provider-c", 1))
    latest = _snapshot(204, "provider-c", AT, 1, 0, 0, 1, 0)
    latest.campaign_v2_id = 8
    active_session.add(latest)
    active_session.add(_observation(204, "6860000001", "SUCCESSFUL", "DELIVERED"))
    active_session.commit()

    report = build_campaign_v2_performance(
        from_date="2026-10-01", to_date="2026-10-31",
        allowed_sucursal_keys=None, session=active_session,
    )
    assert report["campaign_count"] == 2
    assert [row["campaign_id"] for row in report["campaigns"]] == [7, 8]
    assert [row["successful"] for row in report["campaigns"]] == [3, 1]
    assert [row["unique_successful_phones"] for row in report["campaigns"]] == [2, 1]
    assert report["summary"]["successful"] == 4
    assert report["summary"]["unique_successful_phones"] == 2
    assert report["frequency"] == {"once": 1, "twice": 0, "three": 1, "four_plus": 0}
    assert report["summary"]["repeated_successful_phones"] == 1
