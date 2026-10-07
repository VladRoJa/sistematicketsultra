from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import BigInteger, Column, Integer, MetaData, Table, create_engine, event
from sqlalchemy.orm import Session

from app.models.marketing import (
    MarketingCampaignV2BlacklistORM,
    MarketingCampaignV2ORM,
    MarketingCampaignV2ProviderRecipientObservationORM,
    MarketingCampaignV2ProviderStatsSnapshotORM,
    MarketingCampaignV2RecipientEvidenceORM,
    MarketingCampaignV2RecipientORM,
)
from app.services import marketing_campaign_v2_audience_service as audience
from app.services import marketing_campaign_v2_creation_service as creation
from app.services.marketing_campaign_provider import (
    CampaignProviderInteraction,
    CampaignProviderRawCounts,
    CampaignProviderStats,
)
from app.services.marketing_campaign_v2_provider_stats_snapshot_service import (
    capture_campaign_v2_provider_stats_snapshot,
)


NOW = datetime(2026, 10, 1, 18, 0, tzinfo=timezone.utc)
RULE = {
    "delivery_buckets": ["VIEWED"],
    "outcomes": ["FAILED"],
    "button_interacted": True,
    "lookback_days": None,
}


def _definition(scope):
    return {
        "filters": {"allowed_sucursal_keys": scope},
        "preview": {
            "fingerprint": "historical",
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
    MarketingCampaignV2BlacklistORM.__table__.to_metadata(metadata)
    MarketingCampaignV2ORM.__table__.to_metadata(metadata)
    MarketingCampaignV2RecipientORM.__table__.to_metadata(metadata)
    MarketingCampaignV2RecipientEvidenceORM.__table__.to_metadata(metadata)
    MarketingCampaignV2ProviderStatsSnapshotORM.__table__.to_metadata(metadata)
    MarketingCampaignV2ProviderRecipientObservationORM.__table__.to_metadata(metadata)
    metadata.create_all(engine)

    with Session(engine) as value:
        value.add_all(
            [
                MarketingCampaignV2ORM(
                    id=1,
                    name="Historical A",
                    purpose="REACTIVATION",
                    source="EXPIRED_MEMBERS",
                    provider="IVENTAS",
                    provider_campaign_id="provider-a",
                    audience_definition_json=_definition(["BRANCH A"]),
                    frozen_at=NOW,
                    created_at=NOW,
                    updated_at=NOW,
                ),
                MarketingCampaignV2ORM(
                    id=2,
                    name="Historical B",
                    purpose="REACTIVATION",
                    source="EXPIRED_MEMBERS",
                    provider="IVENTAS",
                    provider_campaign_id="provider-b",
                    audience_definition_json=_definition(["BRANCH B"]),
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
                    campaign_id=1,
                    phone_mx10="6861000001",
                    source="EXPIRED_MEMBERS",
                ),
                MarketingCampaignV2RecipientORM(
                    id=11,
                    campaign_id=1,
                    phone_mx10="6861000002",
                    source="EXPIRED_MEMBERS",
                ),
                MarketingCampaignV2RecipientORM(
                    id=12,
                    campaign_id=1,
                    phone_mx10="6861000003",
                    source="EXPIRED_MEMBERS",
                ),
            ]
        )
        value.commit()

        next_ids = {
            MarketingCampaignV2ORM: 1000,
            MarketingCampaignV2RecipientORM: 2000,
            MarketingCampaignV2RecipientEvidenceORM: 3000,
            MarketingCampaignV2ProviderStatsSnapshotORM: 4000,
            MarketingCampaignV2ProviderRecipientObservationORM: 5000,
        }

        @event.listens_for(value, "before_flush")
        def _assign_sqlite_bigint_ids(session_obj, flush_context, instances):
            for row in session_obj.new:
                row_type = type(row)
                if row_type in next_ids and row.id is None:
                    row.id = next_ids[row_type]
                    next_ids[row_type] += 1

        yield value

    engine.dispose()


class FakeProvider:
    def __init__(self, stats):
        self.stats = stats
        self.calls = []

    def get_campaign_stats(self, provider_campaign_id):
        self.calls.append(provider_campaign_id)
        return self.stats

    def capabilities(self):
        raise AssertionError("unused in acceptance")


def _provider_stats(
    *,
    sent=(),
    delivered=(),
    viewed=(),
    failed=(),
    button=(),
    analytics_marker=1,
):
    sent = frozenset(f"mx10:{phone}" for phone in sent)
    delivered = frozenset(f"mx10:{phone}" for phone in delivered)
    viewed = frozenset(f"mx10:{phone}" for phone in viewed)
    failed = frozenset(f"mx10:{phone}" for phone in failed)
    successful = sent | delivered | viewed
    button_phones = frozenset(f"mx10:{phone}" for phone in button)
    interactions = (
        (
            CampaignProviderInteraction(
                label="INFORMACION",
                raw_item_count=len(button_phones),
                unique_recipient_phones=button_phones,
            ),
        )
        if button_phones
        else ()
    )
    return CampaignProviderStats(
        analytics_status="ok",
        analytics={"marker": analytics_marker},
        raw_counts=CampaignProviderRawCounts(
            successful=len(successful),
            failed=len(failed),
            sent=len(sent),
            delivered=len(delivered),
            viewed=len(viewed),
            answered=0,
            interaction_groups=len(interactions),
            interaction_items=len(button_phones),
        ),
        successful_phones=successful,
        failed_phones=failed,
        sent_phones=sent,
        delivered_phones=delivered,
        viewed_phones=viewed,
        button_interactions=interactions,
    )


def _capture(session, campaign_id, stats, *, now):
    provider = FakeProvider(stats)
    result = capture_campaign_v2_provider_stats_snapshot(
        campaign_id=campaign_id,
        allowed_sucursal_keys=None,
        session=session,
        provider_resolver=lambda key: provider,
        now=now,
    )
    assert provider.calls == [f"provider-{'a' if campaign_id == 1 else 'b'}"]
    return result


def _candidate(row_id, phone):
    return audience.MarketingCampaignV2AudienceCandidate(
        source=audience.SOURCE_EXPIRED_MEMBERS,
        source_ref_type="SOCIOS_VENCIDOS_CARTERA",
        source_ref_id=row_id,
        phone_raw=phone,
        phone_mx10=phone,
        member_pin=f"PIN-{row_id}",
        member_name=f"Socio {row_id}",
        sucursal="BRANCH A",
        sucursal_key="BRANCH A",
        tarifa_raw="DOM",
        tarifa_key="DOM",
        categoria_tarifa="Domiciliado",
        audience_family="DOMICILIADO",
        fecha_vencimiento=date(2026, 8, 15),
        current_status=audience.current_status.STATUS_NOT_FOUND,
    )


def _install_source(monkeypatch, candidates):
    result = audience._SourceLoadResult(
        universe_count=len(candidates),
        scoped_count=len(candidates),
        candidates=tuple(candidates),
        current_status_blocked=(),
        current_status_counts={},
        metadata={"fixture": "phase2-acceptance"},
    )
    monkeypatch.setattr(
        audience,
        "_load_expired_source",
        lambda **kwargs: result,
    )
    monkeypatch.setattr(
        audience,
        "_read_v2_tariff_catalog",
        lambda **kwargs: {
            "DOM": ("Domiciliado", "DOMICILIADO"),
        },
    )


def _preview(session, rule):
    return creation.build_campaign_v2_freeze_preview(
        source="EXPIRED_MEMBERS",
        audience_families=["DOMICILIADO"],
        allowed_sucursal_keys=("BRANCH A",),
        expiration_date_from="2026-08-01",
        expiration_date_to="2026-08-31",
        history_exclusion=rule,
        session=session,
    )


def test_phase2_snapshot_history_filter_preview_and_freeze_acceptance(
    session,
    monkeypatch,
):
    candidates = [
        _candidate(101, "6861000001"),
        _candidate(102, "6861000002"),
        _candidate(103, "6861000003"),
        _candidate(104, "6861000004"),
    ]
    _install_source(monkeypatch, candidates)

    visible_stats = _provider_stats(
        sent=("6861000003",),
        viewed=("6861000001",),
        failed=("6861000002",),
        button=("6861000003",),
    )
    first = _capture(session, 1, visible_stats, now=NOW)
    repeated = _capture(
        session,
        1,
        visible_stats,
        now=NOW + timedelta(minutes=5),
    )

    assert first["created"] is True
    assert repeated["created"] is False
    assert repeated["id"] == first["id"]
    assert (
        session.query(MarketingCampaignV2ProviderStatsSnapshotORM)
        .filter_by(campaign_v2_id=1)
        .count()
        == 1
    )
    assert (
        session.query(MarketingCampaignV2ProviderRecipientObservationORM)
        .filter_by(snapshot_id=first["id"])
        .count()
        == 3
    )

    # Same phone D has VIEWED evidence, but only in BRANCH B.
    _capture(
        session,
        2,
        _provider_stats(viewed=("6861000004",)),
        now=NOW + timedelta(minutes=1),
    )

    preview = _preview(session, RULE)

    assert preview["history_excluded_count"] == 3
    assert preview["before_history_filter_count"] == 4
    assert preview["after_history_filter_count"] == 1
    assert preview["unique_recipient_count"] == 1
    assert preview["excluded_by_delivery_bucket"] == {"VIEWED": 1}
    assert preview["excluded_by_outcome"] == {"FAILED": 1}
    assert preview["excluded_by_button_interaction"] == 1

    same_preview = _preview(session, RULE)
    assert same_preview["preview_fingerprint"] == preview["preview_fingerprint"]

    frozen = creation.freeze_campaign_v2(
        name="Phase 2 acceptance",
        purpose="REACTIVATION",
        source="EXPIRED_MEMBERS",
        audience_families=["DOMICILIADO"],
        allowed_sucursal_keys=("BRANCH A",),
        expected_preview_fingerprint=preview["preview_fingerprint"],
        created_by_user_id=7,
        expiration_date_from="2026-08-01",
        expiration_date_to="2026-08-31",
        history_exclusion=RULE,
        session=session,
        now=NOW + timedelta(minutes=6),
    )

    assert frozen["recipient_count"] == 1
    frozen_campaign = session.get(MarketingCampaignV2ORM, frozen["campaign_id"])
    assert [row.phone_mx10 for row in frozen_campaign.recipients] == [
        "6861000004"
    ]
    assert (
        frozen_campaign.audience_definition_json["filters"]["history_exclusion"]
        == RULE
    )


def test_phase2_preview_freeze_detects_new_historical_evidence(
    session,
    monkeypatch,
):
    _install_source(
        monkeypatch,
        [
            _candidate(101, "6861000001"),
            _candidate(104, "6861000004"),
        ],
    )
    initial = _provider_stats(
        sent=("6861000004",),
        viewed=("6861000001",),
    )
    _capture(session, 1, initial, now=NOW)
    preview = _preview(
        session,
        {
            "delivery_buckets": ["VIEWED"],
            "outcomes": [],
            "button_interacted": False,
            "lookback_days": None,
        },
    )

    changed = replace(
        initial,
        analytics={"marker": 2},
        sent_phones=frozenset(),
        delivered_phones=frozenset({"mx10:6861000004"}),
    )
    _capture(
        session,
        1,
        changed,
        now=NOW + timedelta(minutes=10),
    )

    with pytest.raises(creation.MarketingCampaignV2PreviewMismatchError):
        creation.freeze_campaign_v2(
            name="Drift acceptance",
            purpose="REACTIVATION",
            source="EXPIRED_MEMBERS",
            audience_families=["DOMICILIADO"],
            allowed_sucursal_keys=("BRANCH A",),
            expected_preview_fingerprint=preview["preview_fingerprint"],
            created_by_user_id=7,
            expiration_date_from="2026-08-01",
            expiration_date_to="2026-08-31",
            history_exclusion={
                "delivery_buckets": ["VIEWED"],
                "outcomes": [],
                "button_interacted": False,
                "lookback_days": None,
            },
            session=session,
            now=NOW + timedelta(minutes=11),
        )


def test_phase2_history_lookback_uses_inclusive_suite_observation_window(
    session,
    monkeypatch,
):
    phone = "6861000001"
    _install_source(monkeypatch, [_candidate(101, phone)])

    _capture(
        session,
        1,
        _provider_stats(viewed=(phone,), analytics_marker=1),
        now=NOW - timedelta(days=100),
    )
    _capture(
        session,
        1,
        _provider_stats(sent=(phone,), analytics_marker=2),
        now=NOW,
    )

    all_history = _preview(
        session,
        {
            "delivery_buckets": ["VIEWED"],
            "outcomes": [],
            "button_interacted": False,
            "lookback_days": None,
        },
    )
    recent_history = _preview(
        session,
        {
            "delivery_buckets": ["VIEWED"],
            "outcomes": [],
            "button_interacted": False,
            "lookback_days": 90,
        },
    )

    assert all_history["history_excluded_count"] == 1
    assert all_history["unique_recipient_count"] == 0
    assert recent_history["history_excluded_count"] == 0
    assert recent_history["unique_recipient_count"] == 1
    evaluation = recent_history["source_metadata"]["history_evaluation"]
    assert evaluation["observed_before"] == NOW.isoformat()
    assert evaluation["observed_after"] == (
        NOW - timedelta(days=90)
    ).isoformat()
