from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import BigInteger, Column, Integer, String, MetaData, Table, create_engine, event, text
from sqlalchemy.orm import Session

from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2ProviderRecipientObservationORM,
    MarketingCampaignV2ProviderStatsSnapshotORM,
    MarketingCampaignV2RecipientEvidenceORM,
    MarketingCampaignV2RecipientORM,
)
from app.services.marketing_campaign_v2_query_service import (
    MarketingCampaignV2NotFoundError,
)
from app.services.marketing_campaign_v2_reporting_cost_service import (
    extract_campaign_cost_projection,
)
from app.services.marketing_campaign_v2_reporting_service import (
    build_campaign_v2_individual_report,
)


BASE = datetime(2026, 10, 1, 18, 0, tzinfo=timezone.utc)


def _definition(scope):
    return {
        "filters": {"allowed_sucursal_keys": scope},
        "preview": {
            "fingerprint": "freeze",
            "fingerprint_version": "campaign-v2-freeze-v1",
        },
    }


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("users", metadata, Column("id", Integer, primary_key=True))
    Table(
        "socios_vencidos_cartera",
        metadata,
        Column("id", BigInteger, primary_key=True),
    )
    Table(
        "socios_activos_snapshot_rows",
        metadata,
        Column("id", BigInteger, primary_key=True),
    )
    Table(
        "socios_activos_snapshots",
        metadata,
        Column("id", BigInteger, primary_key=True),
    )
    MarketingCampaignV2ORM.__table__.to_metadata(metadata)
    Table(
        "marketing_campaign_v2_provider_campaigns",
        metadata,
        Column("id", BigInteger, primary_key=True),
        Column("campaign_v2_id", BigInteger, nullable=False),
        Column("provider", String, nullable=False),
        Column("provider_campaign_id", String),
        Column("status", String, nullable=False),
        Column("recipient_count", Integer, nullable=False),
        Column("sucursal_canon", String, nullable=False),
    )
    MarketingCampaignV2RecipientORM.__table__.to_metadata(metadata)
    MarketingCampaignV2RecipientEvidenceORM.__table__.to_metadata(metadata)
    MarketingCampaignV2ProviderStatsSnapshotORM.__table__.to_metadata(metadata)
    MarketingCampaignV2ProviderRecipientObservationORM.__table__.to_metadata(
        metadata
    )
    metadata.create_all(engine)

    with Session(engine) as value:
        value.add_all(
            [
                _campaign(1, "Reportable", ["BRANCH A"]),
                _campaign(2, "Zero recipients", ["BRANCH A"]),
                _campaign(3, "No snapshot", ["BRANCH A"]),
                _campaign(4, "Outside", ["BRANCH B"]),
            ]
        )
        value.add_all(
            [
                _recipient(10, 1, "6861111111", "BRANCH A", "DOMICILIADO"),
                _recipient(11, 1, "6862222222", "BRANCH A", "DOMICILIADO"),
                _recipient(12, 1, "6863333333", "BRANCH A", "CONVENIO"),
                _recipient(13, 1, "6864444444", None, None),
                _recipient(14, 1, "6865555555", None, None),
                _recipient(30, 3, "6867777777", "BRANCH A", "TRIMESTRAL"),
                _recipient(31, 3, "6868888888", "BRANCH A", "TRIMESTRAL"),
            ]
        )
        value.flush()
        value.add(
            MarketingCampaignV2RecipientEvidenceORM(
                id=1,
                recipient_id=14,
                evidence_order=0,
                source="EXPIRED_MEMBERS",
                phone_raw="6865555555",
                phone_mx10="6865555555",
                sucursal="Branch A",
                sucursal_key="BRANCH A",
                audience_family="SEMESTRE",
                evidence_json=[],
                created_at=BASE,
            )
        )

        old = _snapshot(
            99,
            campaign_id=1,
            fetched_at=BASE,
            fingerprint="9" * 64,
            raw=(2, 1, 1, 1, 0, 0, 0, 0),
            coverage=(3, 0, 2),
            analytics={"responders": 4, "interactions": {"freeText": 1}},
        )
        tie_lower = _snapshot(
            100,
            campaign_id=1,
            fetched_at=BASE + timedelta(hours=1),
            fingerprint="a" * 64,
            raw=(4, 2, 2, 1, 1, 3, 1, 5),
            coverage=(4, 1, 1),
            analytics={"responders": 70, "interactions": {"freeText": 15}},
        )
        latest = _snapshot(
            101,
            campaign_id=1,
            fetched_at=BASE + timedelta(hours=1),
            fingerprint="b" * 64,
            raw=(6, 2, 2, 2, 2, 7, 1, 4),
            coverage=(4, 1, 1),
            analytics={
                "responders": 79,
                "interactions": {"freeText": 16},
                "cost": {},
            },
            button_interactions=[
                {
                    "label": "INFORMACION",
                    "raw_item_count": 4,
                    "recipient_phones": [
                        "mx10:6863333333",
                        "mx10:6869999999",
                    ],
                }
            ],
        )
        value.add_all([old, tie_lower, latest])
        value.flush()

        value.add_all(
            [
                _obs(99, "mx10:6861111111", 10, "SUCCESSFUL", "SENT"),
                _obs(99, "mx10:6862222222", 11, "SUCCESSFUL", "DELIVERED"),
                _obs(99, "mx10:6864444444", 13, "FAILED", None),
                _obs(100, "mx10:6861111111", 10, "SUCCESSFUL", "SENT"),
                _obs(100, "mx10:6862222222", 11, "SUCCESSFUL", "DELIVERED"),
                _obs(100, "mx10:6863333333", 12, "SUCCESSFUL", "VIEWED"),
                _obs(100, "mx10:6864444444", 13, "FAILED", None),
                _obs(100, "mx10:6869999999", None, "FAILED", None),
                _obs(101, "mx10:6861111111", 10, "SUCCESSFUL", "SENT"),
                _obs(101, "mx10:6862222222", 11, "SUCCESSFUL", "DELIVERED"),
                _obs(
                    101,
                    "mx10:6863333333",
                    12,
                    "SUCCESSFUL",
                    "VIEWED",
                    ["INFORMACION"],
                ),
                _obs(101, "mx10:6864444444", 13, "FAILED", None),
                _obs(
                    101,
                    "mx10:6869999999",
                    None,
                    "FAILED",
                    None,
                    ["INFORMACION"],
                ),
            ]
        )
        value.commit()
        yield value

    engine.dispose()


def _campaign(campaign_id, name, scope):
    return MarketingCampaignV2ORM(
        id=campaign_id,
        name=name,
        purpose="REACTIVATION",
        source="EXPIRED_MEMBERS",
        provider="IVENTAS",
        provider_campaign_id=f"external-{campaign_id}",
        audience_definition_json=_definition(scope),
        frozen_at=BASE,
        created_at=BASE,
        updated_at=BASE,
    )


def _recipient(recipient_id, campaign_id, phone, branch, family):
    return MarketingCampaignV2RecipientORM(
        id=recipient_id,
        campaign_id=campaign_id,
        phone_mx10=phone,
        source="EXPIRED_MEMBERS",
        sucursal=branch,
        audience_family=family,
        created_at=BASE,
    )


def _snapshot(
    snapshot_id,
    *,
    campaign_id,
    fetched_at,
    fingerprint,
    raw,
    coverage,
    analytics,
    button_interactions=None,
):
    (
        successful,
        failed,
        sent,
        delivered,
        viewed,
        answered,
        interaction_groups,
        interaction_items,
    ) = raw
    matched, unmatched, without_status = coverage
    return MarketingCampaignV2ProviderStatsSnapshotORM(
        id=snapshot_id,
        campaign_v2_id=campaign_id,
        provider="IVENTAS",
        provider_campaign_id=f"external-{campaign_id}",
        analytics_status="ok",
        fetched_at=fetched_at,
        raw_successful=successful,
        raw_failed=failed,
        raw_sent=sent,
        raw_delivered=delivered,
        raw_viewed=viewed,
        raw_answered=answered,
        raw_interaction_groups=interaction_groups,
        raw_interaction_items=interaction_items,
        analytics_json=analytics,
        button_interactions_json=button_interactions or [],
        provider_recipient_count=matched + unmatched,
        matched_recipient_count=matched,
        unmatched_provider_count=unmatched,
        frozen_recipient_without_provider_status_count=without_status,
        fingerprint=fingerprint,
        created_at=fetched_at,
    )


def _obs(
    snapshot_id,
    phone,
    recipient_id,
    outcome,
    delivery_bucket,
    labels=None,
):
    return MarketingCampaignV2ProviderRecipientObservationORM(
        snapshot_id=snapshot_id,
        normalized_phone=phone,
        campaign_recipient_id=recipient_id,
        outcome=outcome,
        delivery_bucket=delivery_bucket,
        button_labels_json=labels or [],
        created_at=BASE,
    )


def _report(session, campaign_id=1, scope=("BRANCH A",)):
    return build_campaign_v2_individual_report(
        campaign_id=campaign_id,
        allowed_sucursal_keys=scope,
        session=session,
    )


def test_latest_snapshot_uses_fetched_at_then_higher_id(session):
    report = _report(session)

    assert report["observation"] == {
        "snapshot_id": 101,
        "latest_observed_at": (BASE + timedelta(hours=1)).isoformat(),
        "analytics_status": "ok",
        "fingerprint": "b" * 64,
    }


def test_frozen_denominator_normalized_rates_coverage_and_unmatched(session):
    report = _report(session)

    assert report["audience"]["total_recipients"] == 5
    assert report["normalized"] == {
        "successful": 3,
        "failed": 1,
        "sent": 1,
        "delivered": 1,
        "viewed": 1,
        "reach_count": 2,
    }
    assert report["rates"] == {
        "successful_rate": 0.6,
        "reach_rate": 0.4,
        "read_rate": 0.5,
        "failure_rate": 0.2,
    }
    assert report["coverage"] == {
        "matched_recipient_count": 4,
        "unmatched_provider_count": 1,
        "frozen_recipient_without_provider_status_count": 1,
        "status_coverage_rate": 0.8,
    }
    assert (
        report["normalized"]["successful"] + report["normalized"]["failed"]
        < report["audience"]["total_recipients"]
    )


def test_provider_raw_remains_separate_from_normalized(session):
    report = _report(session)

    assert report["provider_raw"] == {
        "successful": 6,
        "failed": 2,
        "sent": 2,
        "delivered": 2,
        "viewed": 2,
        "answered": 7,
        "interaction_groups": 1,
        "interaction_items": 4,
    }
    assert report["provider_raw"]["successful"] != report["normalized"]["successful"]
    assert report["provider_raw"]["failed"] != report["normalized"]["failed"]


def test_button_interactions_separate_raw_items_and_unique_frozen_recipients(session):
    report = _report(session)

    assert report["interactions"]["unique_button_recipients"] == 1
    assert report["interactions"]["button_groups"] == [
        {
            "label": "INFORMACION",
            "unique_recipient_count": 1,
            "raw_item_count": 4,
        }
    ]




def test_duplicate_button_groups_sum_raw_items_without_duplicate_recipient(session):
    latest = session.get(MarketingCampaignV2ProviderStatsSnapshotORM, 101)
    latest.button_interactions_json = [
        {
            "label": "INFORMACION",
            "raw_item_count": 4,
            "recipient_phones": ["mx10:6863333333"],
        },
        {
            "label": "INFORMACION",
            "raw_item_count": 2,
            "recipient_phones": ["mx10:6863333333"],
        },
    ]
    latest.raw_interaction_groups = 2
    latest.raw_interaction_items = 6
    session.commit()

    report = _report(session)

    assert report["interactions"]["unique_button_recipients"] == 1
    assert report["interactions"]["button_groups"] == [
        {
            "label": "INFORMACION",
            "unique_recipient_count": 1,
            "raw_item_count": 6,
        }
    ]


def test_analytics_aggregates_and_cost_unavailable(session):
    report = _report(session)

    assert report["interactions"]["responders_aggregate"] == 79
    assert report["interactions"]["free_text_aggregate"] == 16
    assert report["cost"] == {
        "status": "unavailable",
        "currency": None,
        "total": None,
    }


@pytest.mark.parametrize(
    "analytics",
    [
        None,
        {},
        {"cost": {}},
        {"cost": {"currency": "MXN", "real": {"total": 100}}},
    ],
)
def test_cost_projection_never_invents_unsupported_fields(analytics):
    assert extract_campaign_cost_projection(analytics) == {
        "status": "unavailable",
        "currency": None,
        "total": None,
    }


def test_malformed_analytics_are_null_not_zero(session):
    latest = session.get(MarketingCampaignV2ProviderStatsSnapshotORM, 101)
    latest.analytics_json = {
        "responders": "79",
        "interactions": {"freeText": False},
        "cost": {},
    }
    session.commit()

    report = _report(session)

    assert report["interactions"]["responders_aggregate"] is None
    assert report["interactions"]["free_text_aggregate"] is None


def test_evolution_uses_each_snapshot_state_and_deterministic_order(session):
    report = _report(session)

    assert [row["snapshot_id"] for row in report["evolution"]] == [99, 100, 101]
    assert report["evolution"][0]["normalized"] == {
        "successful": 2,
        "failed": 1,
        "sent": 1,
        "delivered": 1,
        "viewed": 0,
        "reach_count": 1,
    }
    assert report["evolution"][2]["normalized"] == report["normalized"]
    assert report["evolution"][2]["observed_at"] == (
        BASE + timedelta(hours=1)
    ).isoformat()


def test_dimensions_use_frozen_scope_and_evidence_without_proration(session):
    report = _report(session)

    assert report["dimensions"]["scope"] == {
        "is_global": False,
        "allowed_sucursal_keys": ["BRANCH A"],
    }
    assert report["dimensions"]["branches"] == [
        {"value": "BRANCH A", "recipient_count": 4},
        {"value": "UNKNOWN", "recipient_count": 1},
    ]
    assert report["dimensions"]["audience_families"] == [
        {"value": "CONVENIO", "recipient_count": 1},
        {"value": "DOMICILIADO", "recipient_count": 2},
        {"value": "SEMESTRE", "recipient_count": 1},
        {"value": "UNKNOWN", "recipient_count": 1},
    ]


def test_campaign_without_snapshot_is_valid_and_does_not_complete_from_provider(session):
    report = _report(session, campaign_id=3)

    assert report["audience"]["total_recipients"] == 2
    assert report["observation"] == {
        "snapshot_id": None,
        "latest_observed_at": None,
        "analytics_status": None,
        "fingerprint": None,
    }
    assert report["normalized"] == {
        "successful": 0,
        "failed": 0,
        "sent": 0,
        "delivered": 0,
        "viewed": 0,
        "reach_count": 0,
    }
    assert report["rates"] == {
        "successful_rate": 0.0,
        "reach_rate": 0.0,
        "read_rate": None,
        "failure_rate": 0.0,
    }
    assert report["coverage"] == {
        "matched_recipient_count": 0,
        "unmatched_provider_count": 0,
        "frozen_recipient_without_provider_status_count": 2,
        "status_coverage_rate": 0.0,
    }
    assert report["provider_raw"] is None
    assert report["evolution"] == []


def test_zero_recipient_campaign_has_null_denominator_rates(session):
    report = _report(session, campaign_id=2)

    assert report["audience"]["total_recipients"] == 0
    assert report["rates"] == {
        "successful_rate": None,
        "reach_rate": None,
        "read_rate": None,
        "failure_rate": None,
    }
    assert report["coverage"]["status_coverage_rate"] is None


def test_campaign_outside_scope_is_not_found(session):
    with pytest.raises(MarketingCampaignV2NotFoundError):
        _report(session, campaign_id=4, scope=("BRANCH A",))


def test_same_persisted_state_produces_same_report(session):
    assert _report(session) == _report(session)


def test_reporting_never_calls_provider_readthrough_or_capture(session):
    with (
        patch(
            "app.services.marketing_campaign_v2_provider_stats_service."
            "get_campaign_v2_provider_stats",
            side_effect=AssertionError("Reporting must not call provider"),
        ),
        patch(
            "app.services.marketing_campaign_v2_provider_stats_snapshot_service."
            "capture_campaign_v2_provider_stats_snapshot",
            side_effect=AssertionError("Reporting must not capture provider"),
        ),
    ):
        report = _report(session)

    assert report["observation"]["snapshot_id"] == 101


def test_individual_report_uses_bulk_query_pattern_without_n_plus_one(session):
    statements = []

    def before_cursor_execute(
        _conn,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ):
        statements.append(statement)

    event.listen(
        session.get_bind(),
        "before_cursor_execute",
        before_cursor_execute,
    )
    try:
        report = _report(session)
    finally:
        event.remove(
            session.get_bind(),
            "before_cursor_execute",
            before_cursor_execute,
        )

    assert report["audience"]["total_recipients"] == 5
    # One constant additional query discovers provider children; no N+1.
    assert len(statements) <= 6


def test_individual_report_exposes_two_provider_children_without_losing_legacy(session):
    session.execute(text("""
        INSERT INTO marketing_campaign_v2_provider_campaigns
            (id, campaign_v2_id, provider, provider_campaign_id,
             status, recipient_count, sucursal_canon)
        VALUES
            (101, 1, 'IVENTAS', 'external-1', 'SUBMITTED', 3, 'BRANCH A'),
            (102, 1, 'IVENTAS', 'external-other', 'SUBMITTED', 2, 'BRANCH B')
    """))
    newer = _snapshot(
        201, campaign_id=1, fetched_at=BASE + timedelta(hours=2),
        fingerprint="c" * 64, raw=(2, 0, 0, 2, 0, 0, 0, 0),
        coverage=(2, 0, 3), analytics=None,
    )
    newer.provider_campaign_child_id = 102
    newer.provider_campaign_id = "external-other"
    session.add(newer)
    session.commit()

    report = _report(session)
    child_report = report["provider_children"]
    assert child_report["summary"]["child_count"] == 2
    assert child_report["summary"]["provider_raw"]["successful"] == 8
    assert child_report["summary"]["provider_raw_status"] == "complete"
    assert [row["id"] for row in child_report["children"]] == [101, 102]
    assert child_report["summary"]["cost"]["total"] is None
    # Historical report values still exist for backward compatibility.
    assert report["campaign"]["id"] == 1
