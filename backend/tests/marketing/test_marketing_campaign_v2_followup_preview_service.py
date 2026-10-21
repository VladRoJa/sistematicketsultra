"""Synthetic, read-only OR preview tests for immutable Campaign V2 snapshots."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import BigInteger, Column, Integer, MetaData, Table, create_engine
from sqlalchemy.orm import Session

from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2ProviderRecipientObservationORM,
    MarketingCampaignV2ProviderStatsSnapshotORM,
    MarketingCampaignV2RecipientORM,
)
from app.services.marketing_campaign_v2_query_service import (
    MarketingCampaignV2NotFoundError,
)
from app.services.marketing_campaign_v2_followup_preview_service import (
    FOLLOWUP_PREVIEW_VERSION,
    FollowupPreviewConflictError,
    FollowupPreviewUnavailableError,
    FollowupPreviewValidationError,
    build_followup_preview,
)

NOW = datetime(2026, 10, 20, 17, 0, tzinfo=timezone.utc)
OLDER = datetime(2026, 10, 19, 17, 0, tzinfo=timezone.utc)


def _metadata():
    metadata = MetaData()
    Table("users", metadata, Column("id", Integer, primary_key=True))
    Table("socios_vencidos_cartera", metadata, Column("id", BigInteger, primary_key=True))
    Table("socios_activos_snapshots", metadata, Column("id", BigInteger, primary_key=True))
    Table(
        "socios_activos_snapshot_rows", metadata,
        Column("id", BigInteger, primary_key=True),
        Column("snapshot_id", BigInteger),
    )
    for model in (
        MarketingCampaignV2ORM,
        MarketingCampaignV2RecipientORM,
        MarketingCampaignV2ProviderStatsSnapshotORM,
        MarketingCampaignV2ProviderRecipientObservationORM,
    ):
        model.__table__.to_metadata(metadata)
    return metadata


def _campaign(campaign_id, scope):
    return MarketingCampaignV2ORM(
        id=campaign_id,
        name=f"Fuente {campaign_id}",
        purpose="REACTIVATION",
        source="EXPIRED_MEMBERS",
        audience_definition_json={"filters": {"allowed_sucursal_keys": scope}},
        frozen_at=OLDER, created_at=OLDER, updated_at=OLDER,
    )


def _snapshot(snapshot_id, campaign_id, when):
    return MarketingCampaignV2ProviderStatsSnapshotORM(
        id=snapshot_id,
        campaign_v2_id=campaign_id,
        provider="IVENTAS",
        provider_campaign_id=f"provider-{campaign_id}",
        fetched_at=when, created_at=when,
        raw_successful=0, raw_failed=0, raw_sent=0, raw_delivered=0,
        raw_viewed=0, raw_answered=0, raw_interaction_groups=0,
        raw_interaction_items=0,
        provider_recipient_count=0, matched_recipient_count=0,
        unmatched_provider_count=0, frozen_recipient_without_provider_status_count=0,
        fingerprint=f"{snapshot_id:064x}",
    )


def _observation(snapshot_id, recipient_id, outcome, bucket=None):
    phone = f"68610000{recipient_id:02d}"
    return MarketingCampaignV2ProviderRecipientObservationORM(
        snapshot_id=snapshot_id,
        normalized_phone=f"mx10:{phone}",
        campaign_recipient_id=recipient_id,
        outcome=outcome, delivery_bucket=bucket,
        button_labels_json=[],
        created_at=NOW,
    )


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    _metadata().create_all(engine)
    with Session(engine) as active:
        active.add_all([
            _campaign(2, ["BRANCH A"]),
            _campaign(3, ["BRANCH B"]),
            _campaign(4, ["BRANCH A"]),
        ])
        for id_ in range(10, 16):
            active.add(MarketingCampaignV2RecipientORM(
                id=id_, campaign_id=2,
                phone_mx10=f"68610000{id_:02d}", source="EXPIRED_MEMBERS",
                conflict_fields_json=[],
            ))
        active.add(MarketingCampaignV2RecipientORM(
            id=20, campaign_id=3, phone_mx10="6861000020",
            source="EXPIRED_MEMBERS", conflict_fields_json=[],
        ))
        active.add(MarketingCampaignV2RecipientORM(
            id=21, campaign_id=4, phone_mx10="6861000021",
            source="EXPIRED_MEMBERS", conflict_fields_json=[],
        ))
        active.add_all([
            _snapshot(100, 2, OLDER),
            _snapshot(101, 2, NOW),
            _snapshot(200, 3, NOW),
        ])
        active.add_all([
            _observation(100, 10, "FAILED"),
            _observation(100, 11, "SUCCESSFUL", "VIEWED"),
            _observation(101, 10, "SUCCESSFUL", "VIEWED"),
            _observation(101, 11, "SUCCESSFUL", "DELIVERED"),
            _observation(101, 12, "SUCCESSFUL", "SENT"),
            _observation(101, 13, "FAILED"),
            _observation(101, 14, "SUCCESSFUL", "VIEWED"),
            _observation(200, 20, "FAILED"),
        ])
        active.commit()
        yield active
    engine.dispose()


def _preview(session, statuses, **kwargs):
    return build_followup_preview(
        source_campaign_id=2, selected_statuses=statuses,
        allowed_sucursal_keys=("BRANCH A",),
        session=session, **kwargs,
    )


def test_combined_statuses_use_or_union_and_canonical_fingerprint(session):
    first = _preview(session, ["DELIVERED", "VIEWED"], expected_snapshot_id=101)
    swapped = _preview(session, ["VIEWED", "DELIVERED", "VIEWED"], expected_snapshot_id=101)
    assert first == swapped
    assert first["source_campaign_id"] == 2
    assert first["source_snapshot_id"] == 101
    assert first["source_recipient_count"] == 6
    assert first["candidate_count"] == 3
    assert first["match_mode"] == "ANY"
    assert first["selected_statuses"] == ["DELIVERED", "VIEWED"]
    assert first["preview_fingerprint_version"] == FOLLOWUP_PREVIEW_VERSION
    assert len(first["preview_fingerprint"]) == 64
    assert first["status_counts"] == {
        "VIEWED": 2,
        "DELIVERED": 1,
        "SENT": 1,
        "FAILED": 1,
        "SUCCESSFUL": 0,
        "NO_PROVIDER_STATUS": 1,
    }
    assert first["read_only"] is True
    assert first["campaign_created"] is False
    assert first["send_authorized"] is False
    assert first["sendable_count"] is None
    assert not session.new and not session.dirty
    # No member phone, contact list, or recipient identifier is returned.
    serialized = json.dumps(first)
    for phone in ("6861000010", "6861000011", "6861000014"):
        assert phone not in serialized
    assert "recipient_ids" not in serialized


def test_failed_and_missing_status_are_distinct_and_combinable(session):
    combined = _preview(session, ["FAILED", "NO_PROVIDER_STATUS"])
    failed = _preview(session, ["FAILED"])
    missing = _preview(session, ["NO_PROVIDER_STATUS"])
    assert (combined["candidate_count"], failed["candidate_count"], missing["candidate_count"]) == (2, 1, 1)
    assert combined["preview_fingerprint"] != failed["preview_fingerprint"]


def test_older_snapshot_never_contributes_to_new_selection(session):
    latest = _preview(session, ["FAILED"])
    assert latest["source_snapshot_id"] == 101
    assert latest["candidate_count"] == 1
    assert latest["status_counts"]["VIEWED"] == 2
    assert latest["source_snapshot_fingerprint"] == f"{101:064x}"


@pytest.mark.parametrize("bad", [
    None, "", "VIEWED", [], {}, [1], [None], ["ALL"],
    ["NO_SNAPSHOT"], ["VIEWED", "READ"], ["UNREAD"], [""],
])
def test_invalid_selection_fails_closed(session, bad):
    with pytest.raises(FollowupPreviewValidationError):
        _preview(session, bad)


def test_no_snapshot_and_stale_snapshot_fail_closed(session):
    with pytest.raises(FollowupPreviewConflictError):
        _preview(session, ["VIEWED"], expected_snapshot_id=100)
    with pytest.raises(FollowupPreviewValidationError):
        _preview(session, ["VIEWED"], expected_snapshot_id=True)
    with pytest.raises(FollowupPreviewUnavailableError):
        build_followup_preview(
            source_campaign_id=4,
            selected_statuses=["VIEWED"],
            allowed_sucursal_keys=("BRANCH A",),
            session=session,
        )


def test_snapshot_race_creates_different_preview_fingerprint(session):
    before = _preview(session, ["VIEWED"], expected_snapshot_id=101)
    newer = datetime(2026, 10, 21, 17, 0, tzinfo=timezone.utc)
    session.add(_snapshot(102, 2, newer))
    session.add(_observation(102, 10, "SUCCESSFUL", "VIEWED"))
    session.commit()
    after = _preview(session, ["VIEWED"])
    assert after["source_snapshot_id"] == 102
    assert after["candidate_count"] == 1
    assert before["preview_fingerprint"] != after["preview_fingerprint"]
    with pytest.raises(FollowupPreviewConflictError):
        _preview(session, ["VIEWED"], expected_snapshot_id=101)


def test_scope_is_checked_before_snapshot_and_cross_campaign_obs_never_count(session):
    with pytest.raises(MarketingCampaignV2NotFoundError):
        build_followup_preview(
            source_campaign_id=3,
            selected_statuses=["FAILED"],
            allowed_sucursal_keys=("BRANCH A",),
            session=session,
        )
    with pytest.raises(MarketingCampaignV2NotFoundError):
        build_followup_preview(
            source_campaign_id=2,
            selected_statuses=["VIEWED"],
            allowed_sucursal_keys=("BRANCH B",),
            session=session,
        )
    global_result = build_followup_preview(
        source_campaign_id=2, selected_statuses=["FAILED"],
        allowed_sucursal_keys=None, session=session,
    )
    assert global_result["candidate_count"] == 1


def test_ambiguous_recipient_mapping_fails_without_writing(session):
    session.add(MarketingCampaignV2ProviderRecipientObservationORM(
        snapshot_id=101,
        normalized_phone="mx10:6861999999",
        campaign_recipient_id=10,
        outcome="FAILED", button_labels_json=[],
    ))
    session.commit()
    with pytest.raises(FollowupPreviewConflictError):
        _preview(session, ["VIEWED"])
