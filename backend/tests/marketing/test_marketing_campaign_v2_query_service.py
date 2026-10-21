from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import BigInteger, Column, Integer, MetaData, String, Table, create_engine
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
    MarketingCampaignV2QueryValidationError,
    get_campaign_v2,
    get_campaign_v2_recipient,
    list_campaign_v2,
    list_campaign_v2_recipients,
    update_campaign_v2_purpose,
)


NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def _definition(scope):
    return {
        "filters": {"allowed_sucursal_keys": scope},
        "preview": {
            "fingerprint": "abc",
            "fingerprint_version": "campaign-v2-freeze-v1",
        },
    }


def _metadata():
    metadata = MetaData()
    Table("users", metadata, Column("id", Integer, primary_key=True))
    Table(
        "socios_vencidos_cartera",
        metadata,
        Column("id", BigInteger, primary_key=True),
    )
    Table(
        "socios_activos_snapshots",
        metadata,
        Column("id", BigInteger, primary_key=True),
    )
    Table(
        "socios_activos_snapshot_rows",
        metadata,
        Column("id", BigInteger, primary_key=True),
        Column("snapshot_id", BigInteger),
    )
    MarketingCampaignV2ORM.__table__.to_metadata(metadata)
    MarketingCampaignV2RecipientORM.__table__.to_metadata(metadata)
    MarketingCampaignV2RecipientEvidenceORM.__table__.to_metadata(metadata)
    MarketingCampaignV2ProviderStatsSnapshotORM.__table__.to_metadata(metadata)
    MarketingCampaignV2ProviderRecipientObservationORM.__table__.to_metadata(metadata)
    return metadata


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    metadata = _metadata()
    metadata.create_all(engine)
    with Session(engine) as value:
        value.add_all(
            [
                MarketingCampaignV2ORM(
                    id=1,
                    name="Global",
                    purpose="REACTIVATION",
                    source="EXPIRED_MEMBERS",
                    audience_definition_json=_definition(None),
                    frozen_at=NOW,
                    created_at=NOW,
                    updated_at=NOW,
                ),
                MarketingCampaignV2ORM(
                    id=2,
                    name="A",
                    purpose="ACTIVE_MEMBERS",
                    source="ACTIVE_MEMBERS",
                    provider="IVENTAS",
                    provider_campaign_id="provider-campaign-2",
                    audience_definition_json=_definition(["BRANCH A"]),
                    frozen_at=NOW,
                    created_at=NOW,
                    updated_at=NOW,
                ),
                MarketingCampaignV2ORM(
                    id=3,
                    name="AB",
                    purpose="REACTIVATION",
                    source="EXPIRED_MEMBERS",
                    audience_definition_json=_definition(["BRANCH A", "BRANCH B"]),
                    frozen_at=NOW,
                    created_at=NOW,
                    updated_at=NOW,
                ),
                MarketingCampaignV2ORM(
                    id=4,
                    name="Malformed",
                    purpose="REACTIVATION",
                    source="EXPIRED_MEMBERS",
                    audience_definition_json={"broken": True},
                    frozen_at=NOW,
                    created_at=NOW,
                    updated_at=NOW,
                ),
            ]
        )
        value.add_all(
            [
                MarketingCampaignV2RecipientORM(
                    id=10,
                    campaign_id=2,
                    phone_mx10="6861000001",
                    source="ACTIVE_MEMBERS",
                    member_name="A",
                    conflict_fields_json=[],
                ),
                MarketingCampaignV2RecipientORM(
                    id=11,
                    campaign_id=2,
                    phone_mx10="6861000002",
                    source="ACTIVE_MEMBERS",
                    member_name=None,
                    conflict_fields_json=["member_name"],
                ),
                MarketingCampaignV2RecipientORM(
                    id=20,
                    campaign_id=3,
                    phone_mx10="6861000003",
                    source="EXPIRED_MEMBERS",
                    conflict_fields_json=[],
                ),
            ]
        )
        value.add_all(
            [
                MarketingCampaignV2RecipientEvidenceORM(
                    id=100,
                    recipient_id=10,
                    evidence_order=1,
                    source="ACTIVE_MEMBERS",
                    phone_mx10="6861000001",
                    member_name="second",
                    evidence_json=["B"],
                    created_at=NOW,
                ),
                MarketingCampaignV2RecipientEvidenceORM(
                    id=101,
                    recipient_id=10,
                    evidence_order=0,
                    source="ACTIVE_MEMBERS",
                    phone_mx10="6861000001",
                    member_name="first",
                    evidence_json=["A"],
                    created_at=NOW,
                ),
            ]
        )
        value.commit()
        yield value
    engine.dispose()


def test_partial_scope_hides_global_outside_and_malformed_campaigns(session):
    result = list_campaign_v2(
        allowed_sucursal_keys=("BRANCH A",),
        session=session,
    )
    assert [row["id"] for row in result["rows"]] == [2]
    assert result["rows"][0]["provider"] == "IVENTAS"
    assert result["rows"][0]["provider_campaign_id"] == "provider-campaign-2"


def test_partial_scope_sees_only_campaigns_fully_contained_in_current_scope(session):
    result = list_campaign_v2(
        allowed_sucursal_keys=("BRANCH A", "BRANCH B"),
        session=session,
    )
    assert {row["id"] for row in result["rows"]} == {2, 3}


def test_global_scope_reads_valid_global_and_local_but_denies_malformed(session):
    result = list_campaign_v2(allowed_sucursal_keys=None, session=session)
    assert {row["id"] for row in result["rows"]} == {1, 2, 3}


def test_known_campaign_id_outside_scope_fails_as_not_found(session):
    with pytest.raises(MarketingCampaignV2NotFoundError):
        get_campaign_v2(
            campaign_id=3,
            allowed_sucursal_keys=("BRANCH A",),
            session=session,
        )


def test_campaign_detail_uses_frozen_definition_and_recipient_count(session):
    result = get_campaign_v2(
        campaign_id=2,
        allowed_sucursal_keys=("BRANCH A",),
        session=session,
    )
    assert result["recipient_count"] == 2
    assert result["provider"] == "IVENTAS"
    assert result["provider_campaign_id"] == "provider-campaign-2"
    assert result["audience_definition"] == _definition(["BRANCH A"])
    assert result["preview_fingerprint"] == "abc"


def test_history_exposes_followup_origin_without_changing_regular_campaigns(session):
    session.add(MarketingCampaignV2ORM(
        id=5,
        name="Seguimiento de A",
        purpose="REACTIVATION",
        source="FOLLOWUP_SNAPSHOT_DERIVED",
        audience_definition_json={
            "filters": {"allowed_sucursal_keys": ["BRANCH A"]},
            "followup": {
                "version": "campaign-v2-followup-frozen-v1",
                "source_campaign_id": 2,
                "source_snapshot_id": 101,
            },
        },
        frozen_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    ))
    session.commit()

    result = list_campaign_v2(
        allowed_sucursal_keys=("BRANCH A",), session=session,
    )
    by_id = {row["id"]: row for row in result["rows"]}
    assert by_id[5]["source"] == "FOLLOWUP_SNAPSHOT_DERIVED"
    assert by_id[5]["source_campaign_id"] == 2
    assert by_id[2]["source_campaign_id"] is None
    assert get_campaign_v2(
        campaign_id=5,
        allowed_sucursal_keys=("BRANCH A",),
        session=session,
    )["source_campaign_id"] == 2
    assert set(by_id[5]) - set(by_id[2]) == set()


@pytest.mark.parametrize("malformed_origin", [None, False, 0, -2, "2", 5, [], {}])
def test_history_ignores_invalid_followup_origin_without_guessing_from_name(
    session, malformed_origin,
):
    session.add(MarketingCampaignV2ORM(
        id=5,
        name="Seg. 2 (no inferir)",
        purpose="REACTIVATION",
        source="FOLLOWUP_SNAPSHOT_DERIVED",
        audience_definition_json={
            "filters": {"allowed_sucursal_keys": ["BRANCH A"]},
            "followup": {"source_campaign_id": malformed_origin},
        },
        frozen_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    ))
    session.commit()
    rows = list_campaign_v2(
        allowed_sucursal_keys=("BRANCH A",), session=session,
    )["rows"]
    assert next(row for row in rows if row["id"] == 5)["source_campaign_id"] is None


def test_recipient_list_is_stable_paginated_and_counts_evidence_without_loading_rows(session):
    result = list_campaign_v2_recipients(
        campaign_id=2,
        allowed_sucursal_keys=("BRANCH A",),
        page=1,
        page_size=10,
        session=session,
    )
    assert [row["id"] for row in result["rows"]] == [10, 11]
    assert result["rows"][0]["evidence_count"] == 2
    assert result["rows"][1]["conflict_fields"] == ["member_name"]
    assert result["rows"][0]["provider_status"]["status"] == "NO_SNAPSHOT"
    assert result["rows"][0]["provider_status"]["observed_at"] is None



def _snapshot(snapshot_id, campaign_id, observed_at):
    return MarketingCampaignV2ProviderStatsSnapshotORM(
        id=snapshot_id,
        campaign_v2_id=campaign_id,
        provider="IVENTAS",
        provider_campaign_id=f"provider-campaign-{campaign_id}",
        fetched_at=observed_at,
        raw_successful=0,
        raw_failed=0,
        raw_sent=0,
        raw_delivered=0,
        raw_viewed=0,
        raw_answered=0,
        raw_interaction_groups=0,
        raw_interaction_items=0,
        provider_recipient_count=0,
        matched_recipient_count=0,
        unmatched_provider_count=0,
        frozen_recipient_without_provider_status_count=0,
        fingerprint=f"{snapshot_id:064x}",
        created_at=observed_at,
    )


def test_recipient_status_latest_snapshot_only_and_paginated(session):
    older = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
    newer = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
    session.add_all([
        _snapshot(100, 2, older),
        _snapshot(101, 2, newer),
        _snapshot(200, 3, newer),
    ])
    session.add_all([
        MarketingCampaignV2ProviderRecipientObservationORM(
            snapshot_id=100,
            normalized_phone="mx10:6861000001",
            campaign_recipient_id=10,
            outcome="FAILED",
            button_labels_json=[],
        ),
        MarketingCampaignV2ProviderRecipientObservationORM(
            snapshot_id=101,
            normalized_phone="mx10:6861000001",
            campaign_recipient_id=10,
            outcome="SUCCESSFUL",
            delivery_bucket="VIEWED",
            button_labels_json=["Quiero volver"],
        ),
        MarketingCampaignV2ProviderRecipientObservationORM(
            snapshot_id=200,
            normalized_phone="mx10:6861000003",
            campaign_recipient_id=20,
            outcome="FAILED",
            button_labels_json=[],
        ),
    ])
    session.commit()

    first = list_campaign_v2_recipients(
        campaign_id=2,
        allowed_sucursal_keys=("BRANCH A",),
        page=1, page_size=1, session=session,
    )
    second = list_campaign_v2_recipients(
        campaign_id=2,
        allowed_sucursal_keys=("BRANCH A",),
        page=2, page_size=1, session=session,
    )
    assert first["total"] == second["total"] == 2
    assert first["rows"][0]["id"] == 10
    assert first["rows"][0]["provider_status"] == {
        "status": "VIEWED",
        "snapshot_id": 101,
        "observed_at": newer.replace(tzinfo=None).isoformat(),
        "outcome": "SUCCESSFUL",
        "delivery_bucket": "VIEWED",
        "button_labels": ["Quiero volver"],
    }
    assert second["rows"][0]["id"] == 11
    assert second["rows"][0]["provider_status"]["status"] == "NO_PROVIDER_STATUS"
    assert second["rows"][0]["provider_status"]["snapshot_id"] == 101
    assert second["rows"][0]["provider_status"]["outcome"] is None


def test_recipient_status_failure_is_not_confused_with_no_observation(session):
    observed = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)
    session.add(_snapshot(102, 2, observed))
    session.add(MarketingCampaignV2ProviderRecipientObservationORM(
        snapshot_id=102,
        normalized_phone="mx10:6861000002",
        campaign_recipient_id=11,
        outcome="FAILED",
        delivery_bucket=None,
        button_labels_json=[],
    ))
    session.commit()
    result = list_campaign_v2_recipients(
        campaign_id=2, allowed_sucursal_keys=("BRANCH A",),
        page=1, page_size=10, session=session,
    )
    statuses = {row["id"]: row["provider_status"]["status"] for row in result["rows"]}
    assert statuses == {10: "NO_PROVIDER_STATUS", 11: "FAILED"}
    assert result["rows"][1]["provider_status"]["delivery_bucket"] is None


def _add_filter_fixture(session):
    """Dos snapshots: el filtro jamás debe reutilizar los estados viejos."""
    older = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
    newer = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)
    session.add_all([_snapshot(300, 2, older), _snapshot(301, 2, newer)])
    session.add_all([
        MarketingCampaignV2RecipientORM(
            id=recipient_id,
            campaign_id=2,
            phone_mx10=f"68610000{recipient_id}",
            source="ACTIVE_MEMBERS",
            conflict_fields_json=[],
        )
        for recipient_id in (12, 13, 14, 15)
    ])
    specs = [
        (300, 10, "FAILED", None),
        (300, 11, "SUCCESSFUL", "VIEWED"),
        (301, 10, "SUCCESSFUL", "VIEWED"),
        (301, 11, "FAILED", None),
        (301, 12, "SUCCESSFUL", "VIEWED"),
        (301, 13, "SUCCESSFUL", "SENT"),
        (301, 14, "SUCCESSFUL", "DELIVERED"),
    ]
    session.add_all([
        MarketingCampaignV2ProviderRecipientObservationORM(
            snapshot_id=snapshot_id,
            normalized_phone=(
                "mx10:6861000001" if recipient_id == 10 else
                "mx10:6861000002" if recipient_id == 11 else
                f"mx10:68610000{recipient_id}"
            ),
            campaign_recipient_id=recipient_id,
            outcome=outcome,
            delivery_bucket=bucket,
            button_labels_json=[],
        )
        for snapshot_id, recipient_id, outcome, bucket in specs
    ])
    session.commit()


def test_filter_by_latest_status_before_count_and_pagination(session):
    _add_filter_fixture(session)
    expected = {
        "VIEWED": [10, 12],
        "FAILED": [11],
        "SENT": [13],
        "DELIVERED": [14],
        "NO_PROVIDER_STATUS": [15],
        "SUCCESSFUL": [],
        "NO_SNAPSHOT": [],
    }
    for status, ids in expected.items():
        result = list_campaign_v2_recipients(
            campaign_id=2,
            allowed_sucursal_keys=("BRANCH A",),
            provider_status=status,
            page=1,
            page_size=100,
            session=session,
        )
        assert result["total"] == len(ids), status
        assert [r["id"] for r in result["rows"]] == ids, status
        assert all(r["provider_status"]["status"] == status for r in result["rows"])

    first = list_campaign_v2_recipients(
        campaign_id=2, allowed_sucursal_keys=("BRANCH A",),
        provider_status="VIEWED", page=1, page_size=1, session=session,
    )
    second = list_campaign_v2_recipients(
        campaign_id=2, allowed_sucursal_keys=("BRANCH A",),
        provider_status=" viewed ", page=2, page_size=1, session=session,
    )
    past_end = list_campaign_v2_recipients(
        campaign_id=2, allowed_sucursal_keys=("BRANCH A",),
        provider_status="VIEWED", page=3, page_size=1, session=session,
    )
    assert first["total"] == second["total"] == past_end["total"] == 2
    assert first["total_pages"] == second["total_pages"] == 2
    assert [r["id"] for r in first["rows"]] == [10]
    assert [r["id"] for r in second["rows"]] == [12]
    assert past_end["rows"] == []
    assert first["rows"][0]["evidence_count"] == 2
    assert second["rows"][0]["evidence_count"] == 0
    assert first["rows"][0]["provider_status"]["snapshot_id"] == 301


def test_unfiltered_recipients_are_backwards_compatible(session):
    _add_filter_fixture(session)
    for status in (None, "", "ALL", " all "):
        result = list_campaign_v2_recipients(
            campaign_id=2,
            allowed_sucursal_keys=("BRANCH A",),
            page=1, page_size=100,
            provider_status=status,
            session=session,
        )
        assert result["total"] == 6
        assert result["total_pages"] == 1
        assert [r["id"] for r in result["rows"]] == [10, 11, 12, 13, 14, 15]


def test_filter_no_snapshot_not_equivalent_to_failed_or_unmatched(session):
    no_snapshot = list_campaign_v2_recipients(
        campaign_id=3, allowed_sucursal_keys=("BRANCH A", "BRANCH B"),
        provider_status="NO_SNAPSHOT", session=session,
    )
    assert no_snapshot["total"] == 1
    assert no_snapshot["rows"][0]["provider_status"]["status"] == "NO_SNAPSHOT"
    for status in ("FAILED", "NO_PROVIDER_STATUS", "VIEWED"):
        empty = list_campaign_v2_recipients(
            campaign_id=3, allowed_sucursal_keys=("BRANCH A", "BRANCH B"),
            provider_status=status, session=session,
        )
        assert empty["total"] == 0
        assert empty["rows"] == []


def test_recipient_provider_filter_rejects_invalid_and_preserves_scope(session):
    for bad in ("RESPONDIÓ", "UNREAD", "NOT_VIEWED", "FAILED,VIEWED", "abc", 1, True):
        with pytest.raises(MarketingCampaignV2QueryValidationError):
            list_campaign_v2_recipients(
                campaign_id=2, allowed_sucursal_keys=("BRANCH A",),
                provider_status=bad, session=session,
            )
    with pytest.raises(MarketingCampaignV2NotFoundError):
        list_campaign_v2_recipients(
            campaign_id=3, allowed_sucursal_keys=("BRANCH A",),
            provider_status="FAILED", session=session,
        )


def test_recipient_detail_reads_only_frozen_evidence_in_evidence_order(session):
    result = get_campaign_v2_recipient(
        campaign_id=2,
        recipient_id=10,
        allowed_sucursal_keys=("BRANCH A",),
        session=session,
    )
    assert [row["evidence_order"] for row in result["evidence"]] == [0, 1]
    assert [row["member_name"] for row in result["evidence"]] == ["first", "second"]


def test_recipient_id_from_another_campaign_is_not_disclosed(session):
    with pytest.raises(MarketingCampaignV2NotFoundError):
        get_campaign_v2_recipient(
            campaign_id=2,
            recipient_id=20,
            allowed_sucursal_keys=("BRANCH A",),
            session=session,
        )


def test_purpose_is_only_mutation_and_preserves_frozen_definition_and_frozen_at(session):
    before = get_campaign_v2(
        campaign_id=2,
        allowed_sucursal_keys=("BRANCH A",),
        session=session,
    )
    result = update_campaign_v2_purpose(
        campaign_id=2,
        purpose="NEW_SALE",
        allowed_sucursal_keys=("BRANCH A",),
        session=session,
        now=datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc),
    )
    assert result["purpose"] == "NEW_SALE"
    assert result["frozen_at"] == before["frozen_at"]
    assert result["audience_definition"] == before["audience_definition"]
    assert result["recipient_count"] == before["recipient_count"]


def test_invalid_purpose_and_empty_backend_scope_fail_closed(session):
    with pytest.raises(MarketingCampaignV2QueryValidationError):
        update_campaign_v2_purpose(
            campaign_id=2,
            purpose="SENT",
            allowed_sucursal_keys=("BRANCH A",),
            session=session,
        )
    with pytest.raises(MarketingCampaignV2QueryValidationError):
        list_campaign_v2(allowed_sucursal_keys=(), session=session)


def test_list_filters_and_pagination_are_stable(session):
    result = list_campaign_v2(
        allowed_sucursal_keys=None,
        purpose="REACTIVATION",
        source="EXPIRED_MEMBERS",
        page=1,
        page_size=1,
        session=session,
    )
    assert result["total"] == 2
    assert result["total_pages"] == 2
    assert len(result["rows"]) == 1


def test_query_source_filter_accepts_funnel_portfolio():
    from app.services import marketing_campaign_v2_query_service as service

    assert service._normalize_optional_source("funnel_portfolio") == "FUNNEL_PORTFOLIO"
