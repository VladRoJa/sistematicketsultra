from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import BigInteger, Column, Integer, String, MetaData, Table, create_engine, text
from sqlalchemy.orm import Session

from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2ProviderRecipientObservationORM,
    MarketingCampaignV2ProviderStatsSnapshotORM,
    MarketingCampaignV2RecipientORM,
)
from app.services.marketing_campaign_provider import (
    CampaignProviderInteraction,
    CampaignProviderRawCounts,
    CampaignProviderStats,
)
from app.services import (
    marketing_campaign_v2_provider_stats_scheduler_service as scheduler_service,
)
from app.services.marketing_campaign_v2_provider_stats_scheduler_service import (
    CampaignV2ProviderStatsSelection,
    run_campaign_v2_provider_stats_capture_cycle,
    select_campaign_v2_provider_stats_candidates,
)
from app.services.marketing_campaign_v2_provider_stats_service import (
    MarketingCampaignV2ProviderStatsUpstreamError,
)
from app.services.marketing_campaign_v2_provider_stats_snapshot_service import (
    capture_campaign_v2_provider_stats_snapshot,
)


NOW = datetime(2026, 10, 1, 20, 0, tzinfo=timezone.utc)


def _definition():
    return {
        "filters": {"allowed_sucursal_keys": None},
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
    MarketingCampaignV2ORM.__table__.to_metadata(metadata)
    Table(
        "marketing_campaign_v2_provider_campaigns", metadata,
        Column("id", BigInteger, primary_key=True),
        Column("campaign_v2_id", BigInteger, nullable=False),
        Column("provider", String, nullable=False),
        Column("provider_campaign_id", String),
        Column("status", String, nullable=False),
    )
    MarketingCampaignV2RecipientORM.__table__.to_metadata(metadata)
    MarketingCampaignV2ProviderStatsSnapshotORM.__table__.to_metadata(metadata)
    MarketingCampaignV2ProviderRecipientObservationORM.__table__.to_metadata(metadata)
    metadata.create_all(engine)

    with Session(engine) as value:
        for campaign_id in range(1, 7):
            bound = campaign_id != 4
            value.add(
                MarketingCampaignV2ORM(
                    id=campaign_id,
                    name=f"Campaign {campaign_id}",
                    source="EXPIRED_MEMBERS",
                    provider="IVENTAS" if bound else None,
                    provider_campaign_id=(
                        f"external-{campaign_id}"
                        if bound
                        else None
                    ),
                    audience_definition_json=_definition(),
                    frozen_at=NOW - timedelta(days=20),
                    created_at=NOW - timedelta(days=20),
                    updated_at=NOW - timedelta(days=20),
                )
            )

        value.add(
            MarketingCampaignV2RecipientORM(
                id=101,
                campaign_id=1,
                phone_mx10="6861111111",
                source="EXPIRED_MEMBERS",
            )
        )

        _add_snapshot(
            value,
            campaign_id=2,
            fetched_at=NOW - timedelta(hours=3),
            fingerprint="2" * 64,
        )
        _add_snapshot(
            value,
            campaign_id=3,
            fetched_at=NOW - timedelta(hours=30),
            fingerprint="3" * 64,
        )
        _add_snapshot(
            value,
            campaign_id=5,
            fetched_at=NOW - timedelta(hours=1),
            fingerprint="5" * 64,
        )
        value.commit()
        yield value

    engine.dispose()


def _add_snapshot(
    session,
    *,
    campaign_id,
    fetched_at,
    fingerprint,
):
    session.add(
        MarketingCampaignV2ProviderStatsSnapshotORM(
            campaign_v2_id=campaign_id,
            provider="IVENTAS",
            provider_campaign_id=f"external-{campaign_id}",
            analytics_status="ok",
            fetched_at=fetched_at,
            raw_successful=0,
            raw_failed=0,
            raw_sent=0,
            raw_delivered=0,
            raw_viewed=0,
            raw_answered=0,
            raw_interaction_groups=0,
            raw_interaction_items=0,
            analytics_json=None,
            button_interactions_json=[],
            provider_recipient_count=0,
            matched_recipient_count=0,
            unmatched_provider_count=0,
            frozen_recipient_without_provider_status_count=0,
            fingerprint=fingerprint,
            created_at=fetched_at,
        )
    )


def _stats(*, viewed_phone="mx10:6861111111"):
    return CampaignProviderStats(
        analytics_status="ok",
        analytics={"responders": 1},
        raw_counts=CampaignProviderRawCounts(
            successful=1,
            failed=0,
            sent=0,
            delivered=0,
            viewed=1,
            answered=0,
            interaction_groups=1,
            interaction_items=1,
        ),
        successful_phones=frozenset({viewed_phone}),
        failed_phones=frozenset(),
        sent_phones=frozenset(),
        delivered_phones=frozenset(),
        viewed_phones=frozenset({viewed_phone}),
        button_interactions=(
            CampaignProviderInteraction(
                label="INFORMACION",
                raw_item_count=1,
                unique_recipient_phones=frozenset({viewed_phone}),
            ),
        ),
    )


class MutableProvider:
    def __init__(self, stats):
        self.stats = stats
        self.calls = []

    def get_campaign_stats(self, provider_campaign_id):
        self.calls.append(provider_campaign_id)
        return self.stats

    def capabilities(self):
        raise AssertionError("unused")


def test_selection_excludes_unbound_and_outside_horizon_and_orders_deterministically(
    session,
):
    selection = select_campaign_v2_provider_stats_candidates(
        now=NOW,
        horizon_hours=24,
        max_campaigns=10,
        session=session,
    )

    assert selection.bound_count == 5
    assert selection.skipped_outside_horizon == 1
    assert selection.campaign_ids == (1, 6, 2, 5)
    assert 4 not in selection.campaign_ids
    assert 3 not in selection.campaign_ids


def test_max_campaigns_per_cycle_is_applied_after_deterministic_order(session):
    selection = select_campaign_v2_provider_stats_candidates(
        now=NOW,
        horizon_hours=24,
        max_campaigns=2,
        session=session,
    )

    assert selection.campaign_ids == (1, 6)
    assert selection.eligible_count == 4
    assert selection.skipped_by_limit == 2


def test_identical_stats_become_unchanged_and_changed_stats_create_new_snapshot(
    session,
):
    for campaign_id in (2, 3, 5, 6):
        campaign = session.get(MarketingCampaignV2ORM, campaign_id)
        campaign.provider = None
        campaign.provider_campaign_id = None
    session.commit()

    provider = MutableProvider(_stats())

    def capture(**kwargs):
        return capture_campaign_v2_provider_stats_snapshot(
            **kwargs,
            provider_resolver=lambda key: provider,
        )

    first = run_campaign_v2_provider_stats_capture_cycle(
        now=NOW,
        horizon_hours=24,
        max_campaigns=1,
        session=session,
        capture_func=capture,
    )
    second = run_campaign_v2_provider_stats_capture_cycle(
        now=NOW + timedelta(hours=1),
        horizon_hours=24,
        max_campaigns=1,
        session=session,
        capture_func=capture,
    )

    assert first.created == 1
    assert first.unchanged == 0
    assert second.created == 0
    assert second.unchanged == 1
    assert session.query(MarketingCampaignV2ProviderStatsSnapshotORM).filter_by(
        campaign_v2_id=1
    ).count() == 1
    assert session.query(
        MarketingCampaignV2ProviderRecipientObservationORM
    ).count() == 1

    provider.stats = replace(
        provider.stats,
        analytics={"responders": 2},
    )
    third = run_campaign_v2_provider_stats_capture_cycle(
        now=NOW + timedelta(hours=2),
        horizon_hours=24,
        max_campaigns=1,
        session=session,
        capture_func=capture,
    )

    assert third.created == 1
    assert session.query(MarketingCampaignV2ProviderStatsSnapshotORM).filter_by(
        campaign_v2_id=1
    ).count() == 2


def test_failure_is_isolated_and_next_campaign_continues(session, caplog):
    calls = []

    def capture(**kwargs):
        campaign_id = kwargs["campaign_id"]
        calls.append(campaign_id)
        if campaign_id == 1:
            raise MarketingCampaignV2ProviderStatsUpstreamError(
                "provider-secret-detail",
                retryable=True,
                retry_after_seconds=30,
            )
        return {"created": True}

    result = run_campaign_v2_provider_stats_capture_cycle(
        now=NOW,
        horizon_hours=24,
        max_campaigns=3,
        session=session,
        capture_func=capture,
    )

    assert calls == [1, 6, 2]
    assert result.attempted == 3
    assert result.failed == 1
    assert result.created == 2
    assert "provider-secret-detail" not in caplog.text


@pytest.mark.parametrize(
    "error",
    [
        MarketingCampaignV2ProviderStatsUpstreamError(
            "429",
            retryable=True,
            retry_after_seconds=60,
        ),
        MarketingCampaignV2ProviderStatsUpstreamError(
            "5xx",
            retryable=True,
        ),
        MarketingCampaignV2ProviderStatsUpstreamError(
            "transport",
            retryable=True,
        ),
        MarketingCampaignV2ProviderStatsUpstreamError(
            "parser invariant",
            retryable=False,
        ),
    ],
)
def test_provider_and_parser_failures_are_isolated(session, error):
    attempts = []

    def capture(**kwargs):
        attempts.append(kwargs["campaign_id"])
        if len(attempts) == 1:
            raise error
        return {"created": False}

    result = run_campaign_v2_provider_stats_capture_cycle(
        now=NOW,
        horizon_hours=24,
        max_campaigns=2,
        session=session,
        capture_func=capture,
    )

    assert attempts == [1, 6]
    assert result.failed == 1
    assert result.unchanged == 1


def test_default_db_session_is_removed_after_each_campaign(monkeypatch):
    cleanups = []
    monkeypatch.setattr(
        scheduler_service,
        "select_campaign_v2_provider_stats_candidates",
        lambda **kwargs: CampaignV2ProviderStatsSelection(
            campaign_ids=(10, 20),
            bound_count=2,
            eligible_count=2,
            skipped_outside_horizon=0,
            skipped_by_limit=0,
        ),
    )
    monkeypatch.setattr(
        scheduler_service.db.session,
        "remove",
        lambda: cleanups.append("remove"),
    )

    result = scheduler_service.run_campaign_v2_provider_stats_capture_cycle(
        now=NOW,
        horizon_hours=24,
        max_campaigns=2,
        capture_func=lambda **kwargs: {"created": False},
    )

    assert result.attempted == 2
    assert result.unchanged == 2
    assert cleanups == ["remove", "remove"]

def _insert_child(session, *, child_id, campaign_id, provider_campaign_id, status="SUBMITTED"):
    session.execute(
        text("""
            INSERT INTO marketing_campaign_v2_provider_campaigns
                (id, campaign_v2_id, provider, provider_campaign_id, status)
            VALUES (:child_id, :campaign_id, 'IVENTAS', :provider_campaign_id, :status)
        """),
        {
            "child_id": child_id,
            "campaign_id": campaign_id,
            "provider_campaign_id": provider_campaign_id,
            "status": status,
        },
    )


def test_selection_targets_children_independently_and_applies_global_limit(session):
    _insert_child(session, child_id=101, campaign_id=1, provider_campaign_id="child-a")
    _insert_child(session, child_id=102, campaign_id=1, provider_campaign_id="child-b")
    _insert_child(session, child_id=103, campaign_id=1, provider_campaign_id=None, status="PROVIDER_ERROR")
    _insert_child(session, child_id=201, campaign_id=2, provider_campaign_id="external-2")
    session.commit()

    selection = select_campaign_v2_provider_stats_candidates(
        now=NOW, horizon_hours=24, max_campaigns=4, session=session,
    )
    # Parent-bound campaigns 1 and 2 must not be scheduled again as legacy.
    assert selection.bound_count == 6
    assert selection.eligible_count == 5
    assert selection.campaign_ids == (1, 1, 6, 2)
    assert selection.provider_child_ids == (101, 102, None, 201)
    assert selection.skipped_by_limit == 1


def test_child_horizon_uses_provider_identity_even_for_legacy_snapshot(session):
    _insert_child(session, child_id=101, campaign_id=1, provider_campaign_id="child-a")
    _insert_child(session, child_id=102, campaign_id=1, provider_campaign_id="child-b")
    _add_snapshot(
        session, campaign_id=1,
        fetched_at=NOW - timedelta(hours=30), fingerprint="a" * 64,
    )
    old_snapshot = (
        session.query(MarketingCampaignV2ProviderStatsSnapshotORM)
        .filter_by(campaign_v2_id=1).one()
    )
    old_snapshot.provider_campaign_id = "child-a"
    # Historical snapshot has NULL child FK, but must still count for horizon.
    session.commit()

    selection = select_campaign_v2_provider_stats_candidates(
        now=NOW, horizon_hours=24, max_campaigns=10, session=session,
    )
    assert selection.skipped_outside_horizon == 2  # child-a and legacy campaign 3
    assert 101 not in selection.provider_child_ids
    assert 102 in selection.provider_child_ids


def test_capture_cycle_isolates_child_failure_and_continues(session, caplog):
    _insert_child(session, child_id=101, campaign_id=1, provider_campaign_id="child-a")
    _insert_child(session, child_id=102, campaign_id=1, provider_campaign_id="child-b")
    session.commit()
    calls = []

    def capture(**kwargs):
        calls.append((kwargs["campaign_id"], kwargs.get("provider_campaign_child_id")))
        if kwargs.get("provider_campaign_child_id") == 101:
            raise MarketingCampaignV2ProviderStatsUpstreamError(
                "secret-provider-error", retryable=True,
            )
        return {"created": True}

    result = run_campaign_v2_provider_stats_capture_cycle(
        now=NOW, horizon_hours=24, max_campaigns=3,
        session=session, capture_func=capture,
    )
    assert calls == [(1, 101), (1, 102), (6, None)]
    assert result.attempted == 3
    assert result.created == 2
    assert result.failed == 1
    assert "secret-provider-error" not in caplog.text
