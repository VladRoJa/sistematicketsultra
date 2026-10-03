from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import BigInteger, Column, Integer, MetaData, Table, create_engine, event
from sqlalchemy.orm import Session

from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2ProviderRecipientObservationORM,
    MarketingCampaignV2ProviderStatsSnapshotORM,
    MarketingCampaignV2RecipientEvidenceORM,
    MarketingCampaignV2RecipientORM,
)
from app.services.marketing_campaign_v2_reporting_service import (
    MarketingCampaignV2ReportingValidationError,
    build_campaign_v2_consolidated_report,
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
    MarketingCampaignV2RecipientORM.__table__.to_metadata(metadata)
    MarketingCampaignV2RecipientEvidenceORM.__table__.to_metadata(metadata)
    MarketingCampaignV2ProviderStatsSnapshotORM.__table__.to_metadata(metadata)
    MarketingCampaignV2ProviderRecipientObservationORM.__table__.to_metadata(
        metadata
    )
    metadata.create_all(engine)

    with Session(engine) as value:
        campaigns = [
            _campaign(
                1,
                "Small",
                purpose="REACTIVATION",
                source="EXPIRED_MEMBERS",
                provider="IVENTAS",
                scope=["BRANCH A"],
                frozen_at=BASE,
            ),
            _campaign(
                2,
                "Large",
                purpose="NEW_SALE",
                source="FUNNEL_PORTFOLIO",
                provider="IVENTAS",
                scope=["BRANCH A"],
                frozen_at=BASE + timedelta(minutes=1),
            ),
            _campaign(
                3,
                "Without snapshot",
                purpose="ACTIVE_MEMBERS",
                source="ACTIVE_MEMBERS",
                provider="OTHER",
                scope=["BRANCH A"],
                frozen_at=BASE + timedelta(minutes=2),
            ),
            _campaign(
                4,
                "Branch B",
                purpose="REACTIVATION",
                source="EXPIRED_MEMBERS",
                provider="IVENTAS",
                scope=["BRANCH B"],
                frozen_at=BASE + timedelta(minutes=3),
            ),
            _campaign(
                5,
                "Global",
                purpose="REACTIVATION",
                source="EXPIRED_MEMBERS",
                provider="IVENTAS",
                scope=None,
                frozen_at=BASE + timedelta(minutes=4),
            ),
            _campaign(
                6,
                "Multi",
                purpose="REACTIVATION",
                source="EXPIRED_MEMBERS",
                provider="IVENTAS",
                scope=["BRANCH A", "BRANCH B"],
                frozen_at=BASE + timedelta(minutes=5),
            ),
        ]
        value.add_all(campaigns)

        recipients = [
            _recipient(101, 1, "6860000001", "BRANCH A", "DOMICILIADO"),
            _recipient(102, 1, "6860000002", "BRANCH A", "DOMICILIADO"),
        ]
        large_phones = [
            "6860000001",
            "6860000003",
            "6860000004",
            "6860000005",
            "6860000006",
            "6860000007",
            "6860000008",
            "6860000009",
        ]
        for offset, phone in enumerate(large_phones):
            branch = "BRANCH A" if offset < 6 else None
            family = "CONVENIO" if offset < 4 else None
            recipients.append(
                _recipient(
                    200 + offset,
                    2,
                    phone,
                    branch,
                    family,
                )
            )
        recipients.extend(
            [
                _recipient(301, 3, "6860000010", "BRANCH A", "TRIMESTRAL"),
                _recipient(302, 3, "6860000011", None, None),
                _recipient(401, 4, "6860000012", "BRANCH B", "DOMICILIADO"),
                _recipient(501, 5, "6860000013", "BRANCH A", "DOMICILIADO"),
                _recipient(601, 6, "6860000014", "BRANCH A", "DOMICILIADO"),
                _recipient(602, 6, "6860000015", "BRANCH B", "DOMICILIADO"),
            ]
        )
        value.add_all(recipients)
        value.flush()

        value.add_all(
            [
                MarketingCampaignV2RecipientEvidenceORM(
                    id=1,
                    recipient_id=207,
                    evidence_order=0,
                    source="FUNNEL_PORTFOLIO",
                    phone_raw="6860000009",
                    phone_mx10="6860000009",
                    sucursal_key="BRANCH A",
                    audience_family="SEMESTRE",
                    evidence_json=[],
                    created_at=BASE,
                ),
                MarketingCampaignV2RecipientEvidenceORM(
                    id=2,
                    recipient_id=302,
                    evidence_order=0,
                    source="ACTIVE_MEMBERS",
                    phone_raw="6860000011",
                    phone_mx10="6860000011",
                    sucursal_key="BRANCH A",
                    audience_family="ESTUDIANTE",
                    evidence_json=[],
                    created_at=BASE,
                ),
            ]
        )

        snapshots = [
            _snapshot(
                10,
                campaign_id=1,
                fetched_at=BASE + timedelta(hours=1),
                fingerprint="1" * 64,
                raw=(2, 0, 0, 1, 1, 1, 1, 2),
                coverage=(2, 0, 0),
                analytics={
                    "responders": 2,
                    "interactions": {"freeText": 1},
                    "cost": {},
                },
            ),
            _snapshot(
                11,
                campaign_id=1,
                fetched_at=BASE + timedelta(hours=2),
                fingerprint="2" * 64,
                raw=(3, 1, 1, 1, 1, 2, 1, 3),
                coverage=(2, 1, 0),
                analytics={
                    "responders": 3,
                    "interactions": {"freeText": 1},
                    "cost": {},
                },
            ),
            _snapshot(
                20,
                campaign_id=2,
                fetched_at=BASE + timedelta(hours=3),
                fingerprint="3" * 64,
                raw=(5, 3, 2, 2, 1, 4, 1, 5),
                coverage=(4, 1, 4),
                analytics={
                    "responders": 5,
                    "interactions": {"freeText": 2},
                    "cost": {},
                },
            ),
            _snapshot(
                21,
                campaign_id=2,
                fetched_at=BASE + timedelta(hours=3),
                fingerprint="4" * 64,
                raw=(6, 4, 3, 2, 1, 5, 1, 6),
                coverage=(4, 1, 4),
                analytics={
                    "responders": 6,
                    "interactions": {"freeText": 2},
                    "cost": {},
                },
            ),
            _snapshot(
                40,
                campaign_id=4,
                fetched_at=BASE + timedelta(hours=4),
                fingerprint="5" * 64,
                raw=(1, 0, 1, 0, 0, 0, 0, 0),
                coverage=(1, 0, 0),
                analytics={"cost": {}},
            ),
            _snapshot(
                50,
                campaign_id=5,
                fetched_at=BASE + timedelta(hours=5),
                fingerprint="6" * 64,
                raw=(1, 0, 1, 0, 0, 0, 0, 0),
                coverage=(1, 0, 0),
                analytics={"cost": {}},
            ),
            _snapshot(
                60,
                campaign_id=6,
                fetched_at=BASE + timedelta(hours=6),
                fingerprint="7" * 64,
                raw=(2, 0, 2, 0, 0, 0, 0, 0),
                coverage=(2, 0, 0),
                analytics={"cost": {}},
            ),
        ]
        value.add_all(snapshots)
        value.flush()

        value.add_all(
            [
                _obs(11, "mx10:6860000001", 101, "SUCCESSFUL", "DELIVERED", ["CTA"]),
                _obs(11, "mx10:6860000002", 102, "SUCCESSFUL", "VIEWED"),
                _obs(11, "mx10:6860999999", None, "FAILED", None),
                _obs(21, "mx10:6860000001", 200, "SUCCESSFUL", "VIEWED", ["CTA"]),
                _obs(21, "mx10:6860000003", 201, "SUCCESSFUL", "SENT"),
                _obs(21, "mx10:6860000004", 202, "FAILED", None),
                _obs(21, "mx10:6860000005", 203, "FAILED", None),
                _obs(21, "mx10:6860999998", None, "FAILED", None),
                _obs(40, "mx10:6860000012", 401, "SUCCESSFUL", "SENT"),
                _obs(50, "mx10:6860000013", 501, "SUCCESSFUL", "SENT"),
                _obs(60, "mx10:6860000014", 601, "SUCCESSFUL", "SENT"),
                _obs(60, "mx10:6860000015", 602, "SUCCESSFUL", "SENT"),
            ]
        )
        value.commit()
        yield value

    engine.dispose()


def _campaign(
    campaign_id,
    name,
    *,
    purpose,
    source,
    provider,
    scope,
    frozen_at,
):
    return MarketingCampaignV2ORM(
        id=campaign_id,
        name=name,
        purpose=purpose,
        source=source,
        provider=provider,
        provider_campaign_id=f"external-{campaign_id}",
        audience_definition_json=_definition(scope),
        frozen_at=frozen_at,
        created_at=frozen_at,
        updated_at=frozen_at,
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
        button_interactions_json=[],
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


def _report(session, *, scope=("BRANCH A",), **filters):
    return build_campaign_v2_consolidated_report(
        allowed_sucursal_keys=scope,
        filters=filters,
        session=session,
    )


def test_bulk_latest_and_ordering_with_tie_by_id(session):
    report = _report(session)

    assert [row["campaign"]["id"] for row in report["campaigns"]] == [2, 1, 3]
    assert report["campaigns"][0]["observation"]["snapshot_id"] == 21
    assert report["campaigns"][1]["observation"]["snapshot_id"] == 11
    assert report["campaigns"][2]["observation"]["snapshot_id"] is None
    assert all("evolution" not in row for row in report["campaigns"])
    assert all("dimensions" not in row for row in report["campaigns"])


def test_recipient_exposures_do_not_dedupe_cross_campaign(session):
    report = _report(session)

    assert report["summary"]["campaign_count"] == 3
    assert report["summary"]["total_recipients"] == 12
    assert report["campaigns"][0]["audience"]["total_recipients"] == 8
    assert report["campaigns"][1]["audience"]["total_recipients"] == 2
    # 6860000001 existe en Campaign 1 y 2 y aporta dos exposures.


def test_weighted_rates_are_recomputed_from_summed_numerators(session):
    report = _report(session)
    summary = report["summary"]

    assert summary["normalized"] == {
        "successful": 4,
        "failed": 2,
        "sent": 1,
        "delivered": 1,
        "viewed": 2,
        "reach_count": 3,
    }
    assert summary["rates"] == {
        "successful_rate": 4 / 12,
        "reach_rate": 3 / 12,
        "read_rate": 2 / 3,
        "failure_rate": 2 / 12,
    }

    campaign_rates = [
        row["rates"]["successful_rate"]
        for row in report["campaigns"]
        if row["rates"]["successful_rate"] is not None
    ]
    assert summary["rates"]["successful_rate"] != (
        sum(campaign_rates) / len(campaign_rates)
    )


def test_campaign_without_snapshot_contributes_denominator_and_coverage(session):
    report = _report(session)
    summary = report["summary"]

    assert summary["campaigns_with_snapshot"] == 2
    assert summary["campaigns_without_snapshot"] == 1
    assert summary["coverage"] == {
        "matched_recipient_count": 6,
        "unmatched_provider_count": 2,
        "frozen_recipient_without_provider_status_count": 6,
        "status_coverage_rate": 0.5,
    }
    without = next(
        row
        for row in report["campaigns"]
        if row["campaign"]["id"] == 3
    )
    assert without["provider_raw"] is None
    assert without["normalized"]["successful"] == 0
    assert without["coverage"]["frozen_recipient_without_provider_status_count"] == 2


def test_provider_raw_interactions_and_cost_summary_are_separate(session):
    report = _report(session)
    summary = report["summary"]

    assert summary["provider_raw"] == {
        "successful": 9,
        "failed": 5,
        "sent": 4,
        "delivered": 3,
        "viewed": 2,
        "answered": 7,
        "interaction_groups": 2,
        "interaction_items": 9,
    }
    assert summary["normalized"]["successful"] == 4
    assert summary["interactions"] == {
        "button_interaction_recipient_exposures": 2,
        "responders_aggregate": 9,
        "responders_campaigns_with_value": 2,
        "free_text_aggregate": 3,
        "free_text_campaigns_with_value": 2,
    }
    assert summary["cost"] == {
        "status": "unavailable",
        "currency": None,
        "total": None,
    }


def test_branch_and_family_breakdowns_partition_frozen_cohort(session):
    report = _report(session)
    branches = report["breakdowns"]["branches"]
    families = report["breakdowns"]["audience_families"]

    assert sum(row["recipient_exposures"] for row in branches) == 12
    assert sum(row["successful"] for row in branches) == 4
    assert sum(row["failed"] for row in branches) == 2
    assert sum(row["viewed"] for row in branches) == 2
    assert sum(row["reach_count"] for row in branches) == 3

    assert sum(row["recipient_exposures"] for row in families) == 12
    assert sum(row["successful"] for row in families) == 4
    assert sum(row["failed"] for row in families) == 2

    branch_unknown = next(row for row in branches if row["value"] == "UNKNOWN")
    family_unknown = next(row for row in families if row["value"] == "UNKNOWN")
    assert branch_unknown["recipient_exposures"] == 1
    assert family_unknown["recipient_exposures"] == 3


def test_breakdowns_do_not_contain_campaign_level_provider_aggregates(session):
    report = _report(session)
    for group in (
        report["breakdowns"]["branches"],
        report["breakdowns"]["audience_families"],
    ):
        for row in group:
            assert "provider_raw" not in row
            assert "responders_aggregate" not in row
            assert "free_text_aggregate" not in row
            assert "cost" not in row
            assert "unmatched_provider_count" not in row["coverage"]


def test_observed_window_filters_latest_global_snapshot_inclusively(session):
    exact_one = (BASE + timedelta(hours=2)).isoformat()
    exact_two = (BASE + timedelta(hours=3)).isoformat()

    at_from = _report(session, observed_from=exact_two)
    at_to = _report(session, observed_to=exact_one)
    exact = _report(
        session,
        observed_from=exact_one,
        observed_to=exact_two,
    )

    assert [row["campaign"]["id"] for row in at_from["campaigns"]] == [2]
    assert [row["campaign"]["id"] for row in at_to["campaigns"]] == [1]
    assert [row["campaign"]["id"] for row in exact["campaigns"]] == [2, 1]
    assert all(row["campaign"]["id"] != 3 for row in exact["campaigns"])


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"purpose": "NEW_SALE"}, [2]),
        ({"source": "FUNNEL_PORTFOLIO"}, [2]),
        ({"provider": "OTHER"}, [3]),
        ({"snapshot_status": "WITH_SNAPSHOT"}, [2, 1]),
        ({"snapshot_status": "WITHOUT_SNAPSHOT"}, [3]),
    ],
)
def test_v1_filters(session, filters, expected):
    report = _report(session, **filters)
    assert [row["campaign"]["id"] for row in report["campaigns"]] == expected


@pytest.mark.parametrize(
    "filters",
    [
        {"observed_from": "2026-10-01T12:00:00"},
        {"observed_to": "not-a-date"},
        {
            "observed_from": "2026-10-02T00:00:00Z",
            "observed_to": "2026-10-01T00:00:00Z",
        },
        {"purpose": "BAD"},
        {"source": "BAD"},
        {"provider": "X" * 51},
        {"snapshot_status": "BAD"},
        {"branch": "BRANCH A"},
    ],
)
def test_invalid_filters_are_rejected(session, filters):
    with pytest.raises(MarketingCampaignV2ReportingValidationError):
        _report(session, **filters)


def test_scope_visibility_is_applied_before_aggregates(session):
    limited = _report(session, scope=("BRANCH A",))
    global_scope = _report(session, scope=None)
    multi_scope = _report(session, scope=("BRANCH A", "BRANCH B"))

    assert [row["campaign"]["id"] for row in limited["campaigns"]] == [2, 1, 3]
    assert {row["campaign"]["id"] for row in global_scope["campaigns"]} == {
        1,
        2,
        3,
        4,
        5,
        6,
    }
    assert {row["campaign"]["id"] for row in multi_scope["campaigns"]} == {
        1,
        2,
        3,
        4,
        6,
    }
    assert 5 not in {row["campaign"]["id"] for row in multi_scope["campaigns"]}


def test_same_persisted_state_and_filters_produce_same_response(session):
    first = _report(session, purpose="REACTIVATION")
    second = _report(session, purpose="REACTIVATION")
    assert first == second
    assert "generated_at" not in first


def test_provider_boundary_and_m13_are_not_used(session):
    with (
        patch(
            "app.services.marketing_campaign_v2_provider_stats_service."
            "get_campaign_v2_provider_stats",
            side_effect=AssertionError("no provider read-through"),
        ),
        patch(
            "app.services.marketing_campaign_v2_provider_stats_snapshot_service."
            "capture_campaign_v2_provider_stats_snapshot",
            side_effect=AssertionError("no provider capture"),
        ),
        patch(
            "app.services.marketing_campaign_v2_provider_history_service."
            "get_provider_history_for_phones",
            side_effect=AssertionError("no M13"),
        ),
    ):
        report = _report(session)

    assert report["summary"]["campaign_count"] == 3


def _statement_count(session, scope):
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
        report = _report(session, scope=scope)
    finally:
        event.remove(
            session.get_bind(),
            "before_cursor_execute",
            before_cursor_execute,
        )
    return len(statements), report


def test_query_count_is_approximately_constant_not_per_campaign(session):
    one_count, one = _statement_count(session, ("BRANCH B",))
    many_count, many = _statement_count(session, None)

    assert one["summary"]["campaign_count"] == 1
    assert many["summary"]["campaign_count"] == 6
    assert many_count <= one_count + 2
    assert many_count <= 6
