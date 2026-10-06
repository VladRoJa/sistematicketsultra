from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import BigInteger, Column, Integer, MetaData, Table, create_engine
from sqlalchemy.orm import Session

from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2ProviderRecipientObservationORM,
    MarketingCampaignV2ProviderStatsSnapshotORM,
    MarketingCampaignV2RecipientORM,
)
from app.services import marketing_campaign_v2_audience_service as audience
from app.services import marketing_campaign_v2_creation_service as creation


@pytest.fixture(autouse=True)
def _empty_blacklist(monkeypatch):
    monkeypatch.setattr(audience, "get_blacklisted_phones", lambda **_kwargs: set())


BASE = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
PHONES = {
    "A": "6863000001",
    "B": "6863000002",
    "C": "6863000003",
    "D": "6863000004",
}


def _definition(scope):
    return {
        "filters": {"allowed_sucursal_keys": scope},
        "preview": {
            "fingerprint": "freeze",
            "fingerprint_version": "campaign-v2-freeze-v1",
        },
    }


@pytest.fixture
def history_session():
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

    with Session(engine) as session:
        session.add_all(
            [
                _campaign(1, "Campaign VIEWED", ["BRANCH A"]),
                _campaign(2, "Campaign BUTTON", ["BRANCH A"]),
                _campaign(3, "Campaign OUTSIDE", ["BRANCH B"]),
            ]
        )
        session.flush()

        viewed = _snapshot(session, 1, BASE, "1" * 64)
        button = _snapshot(session, 2, BASE + timedelta(hours=1), "2" * 64)
        outside = _snapshot(session, 3, BASE + timedelta(hours=2), "3" * 64)

        # A = VIEWED. C = VIEWED from campaign 1.
        _obs(session, viewed.id, PHONES["A"], "SUCCESSFUL", "VIEWED", [])
        _obs(session, viewed.id, PHONES["C"], "SUCCESSFUL", "VIEWED", [])

        # B = BUTTON. C = BUTTON from campaign 2.
        _obs(session, button.id, PHONES["B"], "SUCCESSFUL", "SENT", ["CTA"])
        _obs(session, button.id, PHONES["C"], "SUCCESSFUL", "SENT", ["CTA"])

        # D has evidence only outside requester scope. It must behave as no history.
        _obs(session, outside.id, PHONES["D"], "SUCCESSFUL", "VIEWED", ["CTA"])

        session.commit()
        yield session

    engine.dispose()


def _campaign(campaign_id, name, scope):
    return MarketingCampaignV2ORM(
        id=campaign_id,
        name=name,
        source="EXPIRED_MEMBERS",
        audience_definition_json=_definition(scope),
        provider="IVENTAS",
        provider_campaign_id=f"ext-{campaign_id}",
        frozen_at=BASE,
        created_at=BASE,
        updated_at=BASE,
    )


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
            normalized_phone=f"mx10:{phone}",
            campaign_recipient_id=None,
            outcome=outcome,
            delivery_bucket=bucket,
            button_labels_json=labels,
            created_at=BASE,
        )
    )


def _candidate(phone, row_id):
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


def _candidates():
    return tuple(
        _candidate(PHONES[key], index)
        for index, key in enumerate(("A", "B", "C", "D"), start=1)
    )


def _install_source(monkeypatch):
    candidates = _candidates()
    monkeypatch.setattr(
        audience,
        "_load_expired_source",
        lambda **_kwargs: audience._SourceLoadResult(
            universe_count=4,
            scoped_count=4,
            candidates=candidates,
            current_status_blocked=(),
            current_status_counts={},
            metadata={"fixture": "m23"},
        ),
    )
    monkeypatch.setattr(
        audience,
        "_read_v2_tariff_catalog",
        lambda **_kwargs: {"DOM": ("Domiciliado", "DOMICILIADO")},
    )


def _targeting(mode, match, *, mixed=False, lookback_days=None):
    return {
        "mode": mode,
        "match": match,
        "delivery_buckets": ["VIEWED"],
        "outcomes": ["SUCCESSFUL"] if mixed else [],
        "button_interacted": True,
        "lookback_days": lookback_days,
    }


def _kwargs(rule, session):
    return {
        "source": "EXPIRED_MEMBERS",
        "audience_families": ["DOMICILIADO"],
        "allowed_sucursal_keys": ("BRANCH A",),
        "expiration_date_from": "2026-08-01",
        "expiration_date_to": "2026-08-31",
        "historical_targeting": rule,
        "session": session,
    }


@pytest.mark.parametrize(
    ("mode", "match", "included", "excluded", "matched"),
    [
        ("INCLUDE", "ALL", {"C"}, {"A", "B", "D"}, {"C"}),
        ("INCLUDE", "ANY", {"A", "B", "C"}, {"D"}, {"A", "B", "C"}),
        ("EXCLUDE", "ALL", {"A", "B", "D"}, {"C"}, {"C"}),
        ("EXCLUDE", "ANY", {"D"}, {"A", "B", "C"}, {"A", "B", "C"}),
    ],
)
def test_m23_contract_matrix_preview_detail_and_recipients(
    monkeypatch,
    history_session,
    mode,
    match,
    included,
    excluded,
    matched,
):
    _install_source(monkeypatch)
    rule = _targeting(mode, match)

    preview = audience.build_campaign_v2_audience_preview(
        **_kwargs(rule, history_session)
    )

    assert preview["before_history_filter_count"] == 4
    assert preview["history_matched_count"] == len(matched)
    assert preview["history_not_matched_count"] == 4 - len(matched)
    assert preview["history_included_count"] == len(included)
    assert preview["history_excluded_count"] == len(excluded)
    assert preview["after_history_filter_count"] == len(included)
    assert (
        preview["history_matched_count"]
        + preview["history_not_matched_count"]
        == preview["before_history_filter_count"]
    )
    assert (
        preview["history_included_count"]
        + preview["history_excluded_count"]
        == preview["before_history_filter_count"]
    )
    assert (
        preview["history_included_count"]
        == preview["after_history_filter_count"]
    )

    included_detail = audience.build_campaign_v2_audience_preview_detail(
        bucket="HISTORY_INCLUDED",
        page=1,
        page_size=50,
        **_kwargs(rule, history_session),
    )
    excluded_detail = audience.build_campaign_v2_audience_preview_detail(
        bucket="HISTORY_EXCLUDED",
        page=1,
        page_size=50,
        **_kwargs(rule, history_session),
    )
    recipients = audience.build_campaign_v2_audience_preview_detail(
        bucket="RECIPIENTS",
        page=1,
        page_size=50,
        **_kwargs(rule, history_session),
    )

    assert {
        row["phone_mx10"] for row in included_detail["rows"]
    } == {PHONES[key] for key in included}
    assert {
        row["phone_mx10"] for row in excluded_detail["rows"]
    } == {PHONES[key] for key in excluded}
    assert {
        row["phone_mx10"] for row in recipients["rows"]
    } == {PHONES[key] for key in included}

    for row in included_detail["rows"]:
        assert row["history_decision"] == "INCLUDED"
        assert isinstance(row["history_matched"], bool)
        assert isinstance(row["history_reasons"], list)
    for row in excluded_detail["rows"]:
        assert row["history_decision"] == "EXCLUDED"
        assert isinstance(row["history_matched"], bool)
        assert isinstance(row["history_reasons"], list)

    by_phone = {
        row["phone_mx10"]: row
        for row in (*included_detail["rows"], *excluded_detail["rows"])
    }
    assert by_phone[PHONES["D"]]["history_matched"] is False
    assert by_phone[PHONES["D"]]["history_reasons"] == []


def test_cross_campaign_all_explains_partial_and_complete_reasons(
    monkeypatch,
    history_session,
):
    _install_source(monkeypatch)
    rule = _targeting("INCLUDE", "ALL")

    included_detail = audience.build_campaign_v2_audience_preview_detail(
        bucket="HISTORY_INCLUDED",
        page=1,
        page_size=50,
        **_kwargs(rule, history_session),
    )
    excluded_detail = audience.build_campaign_v2_audience_preview_detail(
        bucket="HISTORY_EXCLUDED",
        page=1,
        page_size=50,
        **_kwargs(rule, history_session),
    )

    assert [row["phone_mx10"] for row in included_detail["rows"]] == [
        PHONES["C"]
    ]
    c = included_detail["rows"][0]
    assert c["history_matched"] is True
    assert set(c["history_reasons"]) == {
        "HISTORY_DELIVERY_VIEWED",
        "HISTORY_BUTTON_INTERACTION",
    }

    excluded = {row["phone_mx10"]: row for row in excluded_detail["rows"]}
    assert excluded[PHONES["A"]]["history_matched"] is False
    assert excluded[PHONES["A"]]["history_reasons"] == [
        "HISTORY_DELIVERY_VIEWED"
    ]
    assert excluded[PHONES["B"]]["history_matched"] is False
    assert excluded[PHONES["B"]]["history_reasons"] == [
        "HISTORY_BUTTON_INTERACTION"
    ]
    assert excluded[PHONES["D"]]["history_reasons"] == []


def test_scope_evidence_outside_scope_produces_no_match_or_reason(
    monkeypatch,
    history_session,
):
    _install_source(monkeypatch)
    rule = _targeting("INCLUDE", "ANY")

    excluded = audience.build_campaign_v2_audience_preview_detail(
        bucket="HISTORY_EXCLUDED",
        page=1,
        page_size=50,
        **_kwargs(rule, history_session),
    )
    d = next(
        row for row in excluded["rows"]
        if row["phone_mx10"] == PHONES["D"]
    )

    assert d["history_matched"] is False
    assert d["history_reasons"] == []
    assert d["history_decision"] == "EXCLUDED"


def test_mixed_delivery_outcome_button_are_atomic_conditions(
    monkeypatch,
    history_session,
):
    _install_source(monkeypatch)
    all_rule = _targeting("INCLUDE", "ALL", mixed=True)
    any_rule = _targeting("INCLUDE", "ANY", mixed=True)

    all_preview = audience.build_campaign_v2_audience_preview(
        **_kwargs(all_rule, history_session)
    )
    any_preview = audience.build_campaign_v2_audience_preview(
        **_kwargs(any_rule, history_session)
    )

    assert all_preview["unique_recipient_count"] == 1
    assert any_preview["unique_recipient_count"] == 3
    assert all_preview["matched_by_delivery_bucket"] == {"VIEWED": 1}
    assert all_preview["matched_by_outcome"] == {"SUCCESSFUL": 1}
    assert all_preview["matched_by_button_interaction"] == 1


def test_no_history_bucket_is_zero_without_historical_rule(
    monkeypatch,
    history_session,
):
    _install_source(monkeypatch)

    detail = audience.build_campaign_v2_audience_preview_detail(
        source="EXPIRED_MEMBERS",
        audience_families=["DOMICILIADO"],
        allowed_sucursal_keys=("BRANCH A",),
        bucket="HISTORY_INCLUDED",
        page=1,
        page_size=50,
        expiration_date_from="2026-08-01",
        expiration_date_to="2026-08-31",
        session=history_session,
    )

    assert detail["total"] == 0
    assert detail["rows"] == []


def test_lookback_removes_old_signal_from_reasons_and_decision(
    monkeypatch,
    history_session,
):
    history_session.add(
        _campaign(4, "Campaign LOOKBACK", ["BRANCH A"])
    )
    history_session.flush()
    old_snapshot = _snapshot(
        history_session,
        4,
        BASE - timedelta(days=10),
        "4" * 64,
    )
    recent_snapshot = _snapshot(
        history_session,
        4,
        BASE + timedelta(days=1),
        "5" * 64,
    )
    old_phone = "6863000005"
    recent_phone = "6863000006"
    _obs(
        history_session,
        old_snapshot.id,
        old_phone,
        "SUCCESSFUL",
        "VIEWED",
        [],
    )
    _obs(
        history_session,
        recent_snapshot.id,
        recent_phone,
        "SUCCESSFUL",
        "VIEWED",
        [],
    )
    history_session.commit()

    candidates = (
        _candidate(old_phone, 5),
        _candidate(recent_phone, 6),
    )
    monkeypatch.setattr(
        audience,
        "_load_expired_source",
        lambda **_kwargs: audience._SourceLoadResult(
            universe_count=2,
            scoped_count=2,
            candidates=candidates,
            current_status_blocked=(),
            current_status_counts={},
            metadata={"fixture": "lookback"},
        ),
    )
    monkeypatch.setattr(
        audience,
        "_read_v2_tariff_catalog",
        lambda **_kwargs: {"DOM": ("Domiciliado", "DOMICILIADO")},
    )
    rule = {
        "mode": "INCLUDE",
        "match": "ANY",
        "delivery_buckets": ["VIEWED"],
        "outcomes": [],
        "button_interacted": False,
        "lookback_days": 2,
    }
    kwargs = _kwargs(rule, history_session)

    preview = audience.build_campaign_v2_audience_preview(**kwargs)
    included = audience.build_campaign_v2_audience_preview_detail(
        bucket="HISTORY_INCLUDED",
        page=1,
        page_size=50,
        **kwargs,
    )
    excluded = audience.build_campaign_v2_audience_preview_detail(
        bucket="HISTORY_EXCLUDED",
        page=1,
        page_size=50,
        **kwargs,
    )

    assert preview["history_matched_count"] == 1
    assert preview["history_not_matched_count"] == 1
    assert preview["source_metadata"]["history_evaluation"] == {
        "observed_before": (BASE + timedelta(days=1)).isoformat(),
        "observed_after": (BASE - timedelta(days=1)).isoformat(),
    }
    assert [row["phone_mx10"] for row in included["rows"]] == [
        recent_phone
    ]
    old_row = excluded["rows"][0]
    assert old_row["phone_mx10"] == old_phone
    assert old_row["history_matched"] is False
    assert old_row["history_reasons"] == []


def test_legacy_history_exclusion_keeps_old_detail_shape(
    monkeypatch,
    history_session,
):
    _install_source(monkeypatch)
    legacy = {
        "delivery_buckets": ["VIEWED"],
        "outcomes": [],
        "button_interacted": True,
        "lookback_days": None,
    }
    kwargs = {
        "source": "EXPIRED_MEMBERS",
        "audience_families": ["DOMICILIADO"],
        "allowed_sucursal_keys": ("BRANCH A",),
        "expiration_date_from": "2026-08-01",
        "expiration_date_to": "2026-08-31",
        "history_exclusion": legacy,
        "session": history_session,
    }

    preview = audience.build_campaign_v2_audience_preview(**kwargs)
    detail = audience.build_campaign_v2_audience_preview_detail(
        bucket="HISTORY_EXCLUDED",
        page=1,
        page_size=50,
        **kwargs,
    )

    assert preview["filters"]["history_exclusion"] == legacy
    assert "historical_targeting" not in preview["filters"]
    assert preview["history_excluded_count"] == 3
    assert preview["excluded_by_delivery_bucket"] == {"VIEWED": 2}
    assert preview["excluded_by_button_interaction"] == 2
    assert {row["phone_mx10"] for row in detail["rows"]} == {
        PHONES["A"],
        PHONES["B"],
        PHONES["C"],
    }
    for row in detail["rows"]:
        assert "history_exclusion_reasons" in row
        assert row["history_matched"] is True
        assert row["history_decision"] == "EXCLUDED"
        assert row["history_reasons"] == row["history_exclusion_reasons"]
