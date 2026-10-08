from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import BigInteger, Column, Integer, MetaData, String, Table, create_engine, event, text
from sqlalchemy.orm import Session

from app.models.marketing import (
    MarketingCampaignV2ProviderRecipientObservationORM as Observation,
    MarketingCampaignV2ProviderStatsSnapshotORM as Snapshot,
)
from app.services.marketing_campaign_v2_provider_children_aggregate_service import (
    load_campaign_v2_provider_children_aggregates,
)


NOW = datetime(2026, 10, 8, 18, tzinfo=timezone.utc)


def _snapshot(identifier, *, campaign_id, child_id, raw, minutes=0, linked=True):
    return Snapshot(
        id=identifier, campaign_v2_id=campaign_id,
        provider_campaign_child_id=child_id if linked else None,
        provider="IVENTAS", provider_campaign_id=f"external-{child_id}",
        fetched_at=NOW + timedelta(minutes=minutes),
        analytics_status="ok", raw_successful=raw, raw_failed=0,
        raw_sent=raw, raw_delivered=0, raw_viewed=0, raw_answered=0,
        raw_interaction_groups=0, raw_interaction_items=0,
        analytics_json=None, button_interactions_json=[],
        provider_recipient_count=raw, matched_recipient_count=raw,
        unmatched_provider_count=0,
        frozen_recipient_without_provider_status_count=0,
        fingerprint=f"{identifier:064d}", created_at=NOW,
    )


def test_bulk_loader_picks_latest_snapshot_per_child_with_three_queries():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("marketing_campaign_v2_campaigns", metadata,
          Column("id", BigInteger, primary_key=True))
    Table("marketing_campaign_v2_recipients", metadata,
          Column("id", BigInteger, primary_key=True))
    Table("marketing_campaign_v2_provider_campaigns", metadata,
          Column("id", BigInteger, primary_key=True),
          Column("campaign_v2_id", BigInteger, nullable=False),
          Column("provider", String, nullable=False),
          Column("provider_campaign_id", String),
          Column("status", String, nullable=False),
          Column("recipient_count", Integer, nullable=False),
          Column("sucursal_canon", String, nullable=False))
    Snapshot.__table__.to_metadata(metadata)
    Observation.__table__.to_metadata(metadata)
    metadata.create_all(engine)

    with Session(engine) as session:
        session.execute(text("""
            INSERT INTO marketing_campaign_v2_campaigns (id) VALUES (7), (8)
        """))
        session.execute(text("""
            INSERT INTO marketing_campaign_v2_provider_campaigns
                (id, campaign_v2_id, provider, provider_campaign_id,
                 status, recipient_count, sucursal_canon)
            VALUES
                (1, 7, 'IVENTAS', 'external-1', 'SUBMITTED', 3, 'BRANCH A'),
                (2, 7, 'IVENTAS', 'external-2', 'SUBMITTED', 2, 'BRANCH B'),
                (3, 8, 'IVENTAS', 'external-3', 'SCHEDULED', 1, 'BRANCH C')
        """))
        session.add_all([
            _snapshot(101, campaign_id=7, child_id=1, raw=1, minutes=-10),
            _snapshot(102, campaign_id=7, child_id=1, raw=3, minutes=0),
            _snapshot(103, campaign_id=7, child_id=2, raw=2, linked=False),
        ])
        session.flush()
        session.add_all([
            Observation(snapshot_id=102, normalized_phone="mx10:6861111111",
                        campaign_recipient_id=None, outcome="SUCCESSFUL",
                        delivery_bucket="SENT", button_labels_json=[]),
            Observation(snapshot_id=103, normalized_phone="mx10:6862222222",
                        campaign_recipient_id=None, outcome="SUCCESSFUL",
                        delivery_bucket="SENT", button_labels_json=[]),
        ])
        session.commit()
        queries = []

        def record(_conn, _cursor, statement, _parameters, _ctx, _many):
            if statement.lstrip().upper().startswith("SELECT"):
                queries.append(statement)

        event.listen(engine, "before_cursor_execute", record)
        try:
            result = load_campaign_v2_provider_children_aggregates(
                campaign_ids=[7, 8], session=session,
            )
        finally:
            event.remove(engine, "before_cursor_execute", record)

        assert len(queries) == 3
        assert result[7]["summary"]["provider_raw"]["successful"] == 5
        assert [row["snapshot_id"] for row in result[7]["children"]] == [102, 103]
        assert result[7]["summary"]["provider_raw_status"] == "complete"
        assert result[8]["summary"]["provider_raw_status"] == "unavailable"
        assert result[8]["summary"]["status"] == "SCHEDULED"
        assert set(result) == {7, 8}

    engine.dispose()


def test_bulk_loader_empty_ids_never_queries_database():
    engine = create_engine("sqlite://")
    with Session(engine) as session:
        assert load_campaign_v2_provider_children_aggregates(
            campaign_ids=[], session=session,
        ) == {}
    engine.dispose()
