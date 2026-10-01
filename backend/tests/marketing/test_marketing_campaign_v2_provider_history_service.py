from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import BigInteger, Column, Integer, MetaData, Table, create_engine, event
from sqlalchemy.orm import Session

from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2ProviderRecipientObservationORM,
    MarketingCampaignV2ProviderStatsSnapshotORM,
    MarketingCampaignV2RecipientORM,
)
from app.services.marketing_campaign_v2_provider_history_service import (
    MarketingCampaignV2ProviderHistoryValidationError,
    get_provider_history_for_phones,
)


BASE = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


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
    MarketingCampaignV2ORM.__table__.to_metadata(metadata)
    MarketingCampaignV2RecipientORM.__table__.to_metadata(metadata)
    MarketingCampaignV2ProviderStatsSnapshotORM.__table__.to_metadata(metadata)
    MarketingCampaignV2ProviderRecipientObservationORM.__table__.to_metadata(metadata)
    metadata.create_all(engine)

    with Session(engine) as value:
        value.add_all(
            [
                MarketingCampaignV2ORM(
                    id=1,
                    name="A",
                    source="EXPIRED_MEMBERS",
                    audience_definition_json=_definition(["BRANCH A"]),
                    provider="IVENTAS",
                    provider_campaign_id="ext-1",
                    frozen_at=BASE,
                    created_at=BASE,
                    updated_at=BASE,
                ),
                MarketingCampaignV2ORM(
                    id=2,
                    name="B",
                    source="EXPIRED_MEMBERS",
                    audience_definition_json=_definition(["BRANCH B"]),
                    provider="IVENTAS",
                    provider_campaign_id="ext-2",
                    frozen_at=BASE,
                    created_at=BASE,
                    updated_at=BASE,
                ),
                MarketingCampaignV2ORM(
                    id=3,
                    name="Global",
                    source="EXPIRED_MEMBERS",
                    audience_definition_json=_definition(None),
                    provider="IVENTAS",
                    provider_campaign_id="ext-3",
                    frozen_at=BASE,
                    created_at=BASE,
                    updated_at=BASE,
                ),
            ]
        )
        value.flush()

        # Campaign 1: SENT -> DELIVERED -> VIEWED for same phone.
        s1 = _snapshot(value, 1, BASE, "1" * 64)
        s2 = _snapshot(value, 1, BASE + timedelta(hours=1), "2" * 64)
        s3 = _snapshot(value, 1, BASE + timedelta(hours=2), "3" * 64)

        _obs(value, s1.id, "mx10:6861111111", "SUCCESSFUL", "SENT", ["INFO"])
        _obs(value, s2.id, "mx10:6861111111", "SUCCESSFUL", "DELIVERED", ["INFO"])
        _obs(value, s3.id, "mx10:6861111111", "SUCCESSFUL", "VIEWED", ["INFO", "PROMO"])

        # Same fetched_at, higher snapshot id must win for latest.
        s4 = _snapshot(value, 1, BASE + timedelta(hours=2), "4" * 64)
        _obs(value, s3.id, "mx10:6867777777", "FAILED", None, [])
        _obs(value, s4.id, "mx10:6867777777", "SUCCESSFUL", "VIEWED", [])

        # Same phone in campaign 2 and a provider-unmatched phone.
        s5 = _snapshot(value, 2, BASE + timedelta(hours=3), "5" * 64)
        _obs(value, s5.id, "mx10:6861111111", "SUCCESSFUL", "VIEWED", [])
        _obs(value, s5.id, "mx10:6642222222", "SUCCESSFUL", "DELIVERED", ["CTA"])

        # Global campaign visible only to global scope under current semantics.
        s6 = _snapshot(value, 3, BASE + timedelta(hours=4), "6" * 64)
        _obs(value, s6.id, "mx10:6861111111", "SUCCESSFUL", "SENT", [])

        value.commit()
        yield value

    engine.dispose()


def _snapshot(session, campaign_id, fetched_at, fingerprint):
    row = MarketingCampaignV2ProviderStatsSnapshotORM(
        campaign_v2_id=campaign_id,
        provider="IVENTAS",
        provider_campaign_id=f"ext-{campaign_id}",
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
    session.add(row)
    session.flush()
    return row


def _obs(session, snapshot_id, phone, outcome, bucket, labels):
    session.add(
        MarketingCampaignV2ProviderRecipientObservationORM(
            snapshot_id=snapshot_id,
            normalized_phone=phone,
            campaign_recipient_id=None,
            outcome=outcome,
            delivery_bucket=bucket,
            button_labels_json=labels,
            created_at=BASE,
        )
    )


def test_latest_and_ever_preserve_exact_observed_states(session):
    result = get_provider_history_for_phones(
        phones=["686-111-1111"],
        allowed_sucursal_keys=("BRANCH A",),
        session=session,
    )

    row = result["rows"][0]
    assert row["normalized_phone"] == "mx10:6861111111"
    assert row["campaign_count"] == 1
    assert row["ever_observed"]["delivery_buckets"] == [
        "DELIVERED",
        "SENT",
        "VIEWED",
    ]
    assert row["ever_observed"]["outcomes"] == [
        "SUCCESSFUL",
    ]
    assert row["ever_observed"]["button_interacted"] is True
    assert row["ever_observed"]["button_labels"] == [
        "INFO",
        "PROMO",
    ]
    latest = row["latest_by_campaign"]
    assert len(latest) == 1
    assert latest[0]["snapshot_id"] == 3
    assert latest[0]["outcome"] == "SUCCESSFUL"
    assert latest[0]["delivery_bucket"] == "VIEWED"


def test_outcome_change_and_same_timestamp_tie_are_preserved(session):
    result = get_provider_history_for_phones(
        phones=["6867777777"],
        allowed_sucursal_keys=("BRANCH A",),
        session=session,
    )
    row = result["rows"][0]

    assert row["ever_observed"]["outcomes"] == [
        "FAILED",
        "SUCCESSFUL",
    ]
    assert row["ever_observed"]["delivery_buckets"] == ["VIEWED"]
    assert row["latest_by_campaign"][0]["snapshot_id"] == 4
    assert row["latest_by_campaign"][0]["outcome"] == "SUCCESSFUL"
    assert row["latest_by_campaign"][0]["delivery_bucket"] == "VIEWED"


def test_same_phone_across_multiple_visible_campaigns_counts_campaigns(session):
    result = get_provider_history_for_phones(
        phones=["6861111111"],
        allowed_sucursal_keys=None,
        session=session,
    )
    row = result["rows"][0]
    assert row["campaign_count"] == 3
    assert [item["campaign_v2_id"] for item in row["latest_by_campaign"]] == [
        3,
        2,
        1,
    ]


def test_cutoff_excludes_later_snapshots_inclusively(session):
    result = get_provider_history_for_phones(
        phones=["6861111111"],
        allowed_sucursal_keys=("BRANCH A",),
        observed_before=BASE + timedelta(hours=1),
        session=session,
    )
    row = result["rows"][0]
    assert row["campaign_count"] == 1
    assert row["ever_observed"]["delivery_buckets"] == [
        "DELIVERED",
        "SENT",
    ]
    assert row["latest_by_campaign"][0]["delivery_bucket"] == "DELIVERED"
    assert row["last_observed_at"] == (
        BASE + timedelta(hours=1)
    ).isoformat()


def test_provider_unmatched_phone_is_still_queryable(session):
    result = get_provider_history_for_phones(
        phones=["mx10:6642222222"],
        allowed_sucursal_keys=("BRANCH B",),
        session=session,
    )
    row = result["rows"][0]
    assert row["campaign_count"] == 1
    assert row["latest_by_campaign"][0]["campaign_v2_id"] == 2
    assert row["ever_observed"]["button_labels"] == ["CTA"]


def test_phone_without_history_returns_empty_evidence_not_negative_response(session):
    result = get_provider_history_for_phones(
        phones=["6869999999"],
        allowed_sucursal_keys=None,
        session=session,
    )
    row = result["rows"][0]
    assert row["campaign_count"] == 0
    assert row["first_observed_at"] is None
    assert row["last_observed_at"] is None
    assert row["ever_observed"] == {
        "outcomes": [],
        "delivery_buckets": [],
        "button_interacted": False,
        "button_labels": [],
    }
    assert "responded" not in row
    assert "no_answer" not in row
    assert "unanswered" not in row


def test_scope_hides_campaigns_outside_backend_scope(session):
    result = get_provider_history_for_phones(
        phones=["6861111111"],
        allowed_sucursal_keys=("BRANCH A",),
        session=session,
    )
    assert [
        item["campaign_v2_id"]
        for item in result["rows"][0]["latest_by_campaign"]
    ] == [1]


def test_bulk_deduplicates_normalized_phones_and_uses_one_read_only_query(session):
    statements = []
    engine = session.get_bind()
    campaign = session.get(MarketingCampaignV2ORM, 1)
    campaign.name = "Dirty but not flushed"
    original_commit = session.commit

    def forbidden_commit():
        raise AssertionError("provider history must not commit")

    session.commit = forbidden_commit

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lstrip().upper())

    event.listen(engine, "before_cursor_execute", capture)
    try:
        result = get_provider_history_for_phones(
            phones=[
                "6861111111",
                "+52 686 111 1111",
                "6642222222",
            ],
            allowed_sucursal_keys=None,
            session=session,
        )
    finally:
        session.commit = original_commit
        event.remove(engine, "before_cursor_execute", capture)

    assert result["phone_count"] == 2
    assert [row["normalized_phone"] for row in result["rows"]] == [
        "mx10:6861111111",
        "mx10:6642222222",
    ]
    assert len(statements) == 1
    assert all(statement.startswith("SELECT") for statement in statements)
    assert campaign in session.dirty


def test_invalid_phone_and_bulk_limit_are_rejected(session):
    with pytest.raises(
        MarketingCampaignV2ProviderHistoryValidationError,
        match="MX10",
    ):
        get_provider_history_for_phones(
            phones=["not-a-phone"],
            allowed_sucursal_keys=None,
            session=session,
        )

    with pytest.raises(
        MarketingCampaignV2ProviderHistoryValidationError,
        match="máximo 100",
    ):
        get_provider_history_for_phones(
            phones=[f"686{i:07d}" for i in range(101)],
            allowed_sucursal_keys=None,
            session=session,
        )


def test_cutoff_requires_timezone(session):
    with pytest.raises(
        MarketingCampaignV2ProviderHistoryValidationError,
        match="zona horaria",
    ):
        get_provider_history_for_phones(
            phones=["6861111111"],
            allowed_sucursal_keys=None,
            observed_before=datetime(2026, 10, 1, 12, 0),
            session=session,
        )
