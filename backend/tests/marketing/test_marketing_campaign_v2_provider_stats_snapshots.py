from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import BigInteger, Column, Integer, MetaData, Table, create_engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
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
from app.services.marketing_campaign_v2_provider_stats_snapshot_service import (
    MarketingCampaignV2ProviderStatsSnapshotPersistenceError,
    capture_campaign_v2_provider_stats_snapshot,
    fingerprint_campaign_provider_stats,
    get_latest_campaign_v2_provider_stats_snapshot,
    list_campaign_v2_provider_stats_snapshots,
)


NOW = datetime(2026, 10, 1, 18, 0, tzinfo=timezone.utc)


def _definition():
    return {
        "filters": {"allowed_sucursal_keys": ["BRANCH A"]},
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
    MarketingCampaignV2RecipientORM.__table__.to_metadata(metadata)
    MarketingCampaignV2ProviderStatsSnapshotORM.__table__.to_metadata(metadata)
    MarketingCampaignV2ProviderRecipientObservationORM.__table__.to_metadata(metadata)
    metadata.create_all(engine)

    with Session(engine) as value:
        value.add(
            MarketingCampaignV2ORM(
                id=1,
                name="M11",
                source="EXPIRED_MEMBERS",
                provider="IVENTAS",
                provider_campaign_id="external-123",
                audience_definition_json=_definition(),
                frozen_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        value.add_all(
            [
                MarketingCampaignV2RecipientORM(
                    id=10,
                    campaign_id=1,
                    phone_mx10="6861111111",
                    source="EXPIRED_MEMBERS",
                ),
                MarketingCampaignV2RecipientORM(
                    id=11,
                    campaign_id=1,
                    phone_mx10="6862222222",
                    source="EXPIRED_MEMBERS",
                ),
                MarketingCampaignV2RecipientORM(
                    id=12,
                    campaign_id=1,
                    phone_mx10="6869999999",
                    source="EXPIRED_MEMBERS",
                ),
            ]
        )
        value.commit()
        yield value

    engine.dispose()


def _stats(*, analytics_status="ok", analytics_marker=1):
    return CampaignProviderStats(
        analytics_status=analytics_status,
        analytics=(
            None
            if analytics_marker is None
            else {"responders": analytics_marker}
        ),
        raw_counts=CampaignProviderRawCounts(
            successful=3,
            failed=1,
            sent=1,
            delivered=1,
            viewed=1,
            answered=0,
            interaction_groups=1,
            interaction_items=3,
        ),
        successful_phones=frozenset({
            "mx10:6861111111",
            "mx10:6862222222",
            "mx10:6863333333",
        }),
        failed_phones=frozenset({
            "mx10:6864444444",
        }),
        sent_phones=frozenset({
            "mx10:6861111111",
        }),
        delivered_phones=frozenset({
            "mx10:6863333333",
        }),
        viewed_phones=frozenset({
            "mx10:6862222222",
        }),
        button_interactions=(
            CampaignProviderInteraction(
                label="INFORMACION",
                raw_item_count=3,
                unique_recipient_phones=frozenset({
                    "mx10:6863333333",
                    "mx10:6861111111",
                }),
            ),
        ),
    )


class FakeProvider:
    def __init__(self, stats):
        self.stats = stats
        self.calls = []

    def get_campaign_stats(self, provider_campaign_id):
        self.calls.append(provider_campaign_id)
        return self.stats

    def capabilities(self):
        raise AssertionError("unused")


def _capture(session, stats, *, now=NOW):
    provider = FakeProvider(stats)
    result = capture_campaign_v2_provider_stats_snapshot(
        campaign_id=1,
        allowed_sucursal_keys=("BRANCH A",),
        session=session,
        provider_resolver=lambda key: provider,
        now=now,
    )
    assert provider.calls == ["external-123"]
    return result


def test_initial_capture_persists_snapshot_observations_and_diagnostics(session):
    result = _capture(session, _stats())

    assert result["created"] is True
    assert len(result["fingerprint"]) == 64
    assert result["diagnostics"] == {
        "provider_recipient_count": 4,
        "matched_recipient_count": 2,
        "unmatched_provider_count": 2,
        "frozen_recipient_without_provider_status_count": 1,
    }
    by_phone = {
        row["normalized_phone"]: row
        for row in result["observations"]
    }
    assert by_phone["mx10:6861111111"]["campaign_recipient_id"] == 10
    assert by_phone["mx10:6862222222"]["campaign_recipient_id"] == 11
    assert by_phone["mx10:6863333333"]["campaign_recipient_id"] is None
    assert by_phone["mx10:6864444444"]["campaign_recipient_id"] is None
    assert by_phone["mx10:6864444444"]["outcome"] == "FAILED"
    assert by_phone["mx10:6864444444"]["delivery_bucket"] is None
    assert by_phone["mx10:6861111111"]["button_labels"] == ["INFORMACION"]
    assert by_phone["mx10:6863333333"]["button_labels"] == ["INFORMACION"]

    assert session.query(MarketingCampaignV2ProviderStatsSnapshotORM).count() == 1
    assert (
        session.query(MarketingCampaignV2ProviderRecipientObservationORM).count()
        == 4
    )


def test_exact_repeat_is_idempotent_noop(session):
    first = _capture(session, _stats(), now=NOW)
    second = _capture(
        session,
        _stats(),
        now=NOW + timedelta(minutes=5),
    )

    assert first["id"] == second["id"]
    assert second["created"] is False
    assert second["fetched_at"] == first["fetched_at"]
    assert session.query(MarketingCampaignV2ProviderStatsSnapshotORM).count() == 1
    assert (
        session.query(MarketingCampaignV2ProviderRecipientObservationORM).count()
        == 4
    )


def test_changed_analytics_creates_new_append_only_snapshot(session):
    first = _capture(session, _stats(analytics_marker=1), now=NOW)
    second = _capture(
        session,
        _stats(analytics_marker=2),
        now=NOW + timedelta(minutes=5),
    )

    assert first["id"] != second["id"]
    assert first["fingerprint"] != second["fingerprint"]
    assert session.query(MarketingCampaignV2ProviderStatsSnapshotORM).count() == 2


def test_changed_delivery_bucket_creates_new_snapshot(session):
    first_stats = _stats()
    changed = replace(
        first_stats,
        delivered_phones=frozenset({"mx10:6862222222"}),
        viewed_phones=frozenset({"mx10:6863333333"}),
    )

    first = _capture(session, first_stats, now=NOW)
    second = _capture(
        session,
        changed,
        now=NOW + timedelta(minutes=1),
    )

    assert first["fingerprint"] != second["fingerprint"]
    assert second["created"] is True


def test_fingerprint_is_stable_for_set_and_interaction_order():
    stats = _stats()
    second_interaction = CampaignProviderInteraction(
        label="QUIERO INFO",
        raw_item_count=1,
        unique_recipient_phones=frozenset({
            "mx10:6862222222",
        }),
    )
    ordered = replace(
        stats,
        button_interactions=(
            stats.button_interactions[0],
            second_interaction,
        ),
    )
    reordered = replace(
        ordered,
        button_interactions=tuple(reversed(ordered.button_interactions)),
        successful_phones=frozenset(
            reversed(sorted(ordered.successful_phones))
        ),
    )
    assert (
        fingerprint_campaign_provider_stats(ordered)
        == fingerprint_campaign_provider_stats(reordered)
    )


def test_not_synced_and_null_analytics_are_persisted(session):
    result = _capture(
        session,
        _stats(
            analytics_status="not_synced",
            analytics_marker=None,
        ),
    )
    assert result["analytics_status"] == "not_synced"
    assert result["analytics"] is None


def test_history_and_latest_are_deterministic(session):
    first = _capture(session, _stats(analytics_marker=1), now=NOW)
    second = _capture(
        session,
        _stats(analytics_marker=2),
        now=NOW + timedelta(minutes=10),
    )

    history = list_campaign_v2_provider_stats_snapshots(
        campaign_id=1,
        allowed_sucursal_keys=("BRANCH A",),
        session=session,
    )
    latest = get_latest_campaign_v2_provider_stats_snapshot(
        campaign_id=1,
        allowed_sucursal_keys=("BRANCH A",),
        session=session,
    )

    assert [row["id"] for row in history["rows"]] == [
        second["id"],
        first["id"],
    ]
    assert latest["id"] == second["id"]


def test_db_failure_rolls_back_snapshot_and_observations(session, monkeypatch):
    original_commit = session.commit

    def failing_commit():
        raise SQLAlchemyError("boom")

    monkeypatch.setattr(session, "commit", failing_commit)

    with pytest.raises(
        MarketingCampaignV2ProviderStatsSnapshotPersistenceError
    ):
        _capture(session, _stats())

    monkeypatch.setattr(session, "commit", original_commit)
    assert session.query(MarketingCampaignV2ProviderStatsSnapshotORM).count() == 0
    assert (
        session.query(MarketingCampaignV2ProviderRecipientObservationORM).count()
        == 0
    )


def test_snapshot_unique_constraint_supports_idempotency(session):
    first = _capture(session, _stats())
    row = session.get(
        MarketingCampaignV2ProviderStatsSnapshotORM,
        first["id"],
    )
    duplicate = MarketingCampaignV2ProviderStatsSnapshotORM(
        campaign_v2_id=row.campaign_v2_id,
        provider=row.provider,
        provider_campaign_id=row.provider_campaign_id,
        analytics_status=row.analytics_status,
        fetched_at=NOW + timedelta(hours=1),
        raw_successful=row.raw_successful,
        raw_failed=row.raw_failed,
        raw_sent=row.raw_sent,
        raw_delivered=row.raw_delivered,
        raw_viewed=row.raw_viewed,
        raw_answered=row.raw_answered,
        raw_interaction_groups=row.raw_interaction_groups,
        raw_interaction_items=row.raw_interaction_items,
        analytics_json=row.analytics_json,
        button_interactions_json=row.button_interactions_json,
        provider_recipient_count=row.provider_recipient_count,
        matched_recipient_count=row.matched_recipient_count,
        unmatched_provider_count=row.unmatched_provider_count,
        frozen_recipient_without_provider_status_count=(
            row.frozen_recipient_without_provider_status_count
        ),
        fingerprint=row.fingerprint,
        created_at=NOW + timedelta(hours=1),
    )
    session.add(duplicate)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
