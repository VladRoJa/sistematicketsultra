from datetime import date, datetime, timedelta, timezone
import inspect
from types import SimpleNamespace

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
from app.services import marketing_campaign_v2_funnel_source_service as funnel_source
from app.services import marketing_campaign_v2_provider_history_service as provider_history


@pytest.fixture(autouse=True)
def _empty_blacklist(monkeypatch):
    monkeypatch.setattr(audience, "get_blacklisted_phones", lambda **_kwargs: set())


BASE = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
ACCESS = SimpleNamespace(is_global=False, branch_ids=(1,))
PHONES = {
    "A": "6863100001",
    "B": "6863100002",
    "C": "6863100003",
    "D": "6863100004",
    "BUYER": "6863100005",
    "ACTIVE": "6863100006",
}
SOURCES = (
    audience.SOURCE_EXPIRED_MEMBERS,
    audience.SOURCE_ACTIVE_MEMBERS,
    audience.SOURCE_FUNNEL_PORTFOLIO,
)
MATRIX = (
    ("INCLUDE", "ALL", {"C"}, {"A", "B", "D"}, {"C"}),
    ("INCLUDE", "ANY", {"A", "B", "C"}, {"D"}, {"A", "B", "C"}),
    ("EXCLUDE", "ALL", {"A", "B", "D"}, {"C"}, {"C"}),
    ("EXCLUDE", "ANY", {"D"}, {"A", "B", "C"}, {"A", "B", "C"}),
)


def _definition(scope):
    return {
        "filters": {"allowed_sucursal_keys": scope},
        "preview": {
            "fingerprint": "freeze",
            "fingerprint_version": creation.PREVIEW_FINGERPRINT_VERSION,
        },
    }


@pytest.fixture
def m25_history_session():
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

        _obs(session, viewed.id, PHONES["A"], "SUCCESSFUL", "VIEWED", [])
        _obs(session, viewed.id, PHONES["C"], "SUCCESSFUL", "VIEWED", [])
        _obs(session, button.id, PHONES["B"], "SUCCESSFUL", "SENT", ["CTA"])
        _obs(session, button.id, PHONES["C"], "SUCCESSFUL", "SENT", ["CTA"])

        # D sólo tiene evidencia fuera del scope actual.
        _obs(session, outside.id, PHONES["D"], "SUCCESSFUL", "VIEWED", ["CTA"])

        session.commit()
        yield session

    engine.dispose()


def _campaign(campaign_id, name, scope):
    return MarketingCampaignV2ORM(
        id=campaign_id,
        name=name,
        source=audience.SOURCE_EXPIRED_MEMBERS,
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


def _member_candidate(source, phone, row_id):
    active = source == audience.SOURCE_ACTIVE_MEMBERS
    return audience.MarketingCampaignV2AudienceCandidate(
        source=source,
        source_ref_type=(
            "SOCIOS_ACTIVOS_SNAPSHOT_ROW"
            if active
            else "SOCIOS_VENCIDOS_CARTERA"
        ),
        source_ref_id=row_id,
        source_snapshot_id=91 if active else None,
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
        fecha_vencimiento=None if active else date(2026, 8, 15),
        current_status=None if active else audience.current_status.STATUS_NOT_FOUND,
    )


def _funnel_candidate(phone, contact_id):
    return funnel_source.MarketingCampaignV2FunnelCandidate(
        phone_raw=phone,
        phone_mx10=phone,
        contact_id=contact_id,
        sucursal_id=1,
        sucursal_key="BRANCH A",
        channel="WhatsApp",
        source_date="2026-09-15",
        origin="iVentas / Meta Ads",
        source_reference=f"1:{contact_id}",
    )


def _member_source_result(source, *, duplicate_c=False):
    rows = [
        _member_candidate(source, PHONES[key], index)
        for index, key in enumerate(("A", "B", "C", "D"), start=1)
    ]
    if duplicate_c:
        rows.append(_member_candidate(source, PHONES["C"], 99))
    return audience._SourceLoadResult(
        universe_count=len(rows),
        scoped_count=len(rows),
        candidates=tuple(rows),
        current_status_blocked=(),
        current_status_counts={},
        metadata={"fixture": "m25", "source": source},
    )


def _funnel_result():
    rows = tuple(
        _funnel_candidate(PHONES[key], key)
        for key in ("A", "B", "C", "D")
    )
    active = _funnel_candidate(PHONES["ACTIVE"], "ACTIVE")
    buyer = _funnel_candidate(PHONES["BUYER"], "BUYER")
    return funnel_source.MarketingCampaignV2FunnelSourceResult(
        funnel_month="2026-09",
        funnel_cutoff_date="2026-09-30",
        universe_count=6,
        scoped_count=4,
        funnel_candidates=(*rows, active),
        buyer_excluded=(buyer,),
        invalid_phone=(),
        active_member_suppressed=(active,),
        candidates=rows,
        metadata={
            "funnel_month": "2026-09",
            "funnel_cutoff_date": "2026-09-30",
            "iventas_sync_run_id": 77,
            "active_members_snapshot_id": 900,
            "active_members_cutoff_date": "2026-09-30",
        },
    )


def _install_source(monkeypatch, source, *, duplicate_c=False):
    if source == audience.SOURCE_EXPIRED_MEMBERS:
        monkeypatch.setattr(
            audience,
            "_load_expired_source",
            lambda **_kwargs: _member_source_result(
                source,
                duplicate_c=duplicate_c,
            ),
        )
    elif source == audience.SOURCE_ACTIVE_MEMBERS:
        monkeypatch.setattr(
            audience,
            "_load_active_source",
            lambda **_kwargs: _member_source_result(
                source,
                duplicate_c=duplicate_c,
            ),
        )
    else:
        monkeypatch.setattr(
            audience.funnel_source,
            "load_campaign_v2_funnel_source",
            lambda **_kwargs: _funnel_result(),
        )

    monkeypatch.setattr(
        audience,
        "_read_v2_tariff_catalog",
        lambda **_kwargs: {"DOM": ("Domiciliado", "DOMICILIADO")},
    )


def _rule(mode, match, *, mixed=False, lookback_days=None):
    return {
        "mode": mode,
        "match": match,
        "delivery_buckets": ["VIEWED"],
        "outcomes": ["SUCCESSFUL"] if mixed else [],
        "button_interacted": True,
        "lookback_days": lookback_days,
    }


def _kwargs(source, rule):
    common = {
        "source": source,
        "allowed_sucursal_keys": ("BRANCH A",),
        "historical_targeting": rule,
    }
    if source == audience.SOURCE_EXPIRED_MEMBERS:
        return {
            **common,
            "audience_families": ["DOMICILIADO"],
            "expiration_date_from": "2026-08-01",
            "expiration_date_to": "2026-08-31",
        }
    if source == audience.SOURCE_ACTIVE_MEMBERS:
        return {
            **common,
            "audience_families": ["DOMICILIADO"],
        }
    return {
        **common,
        "audience_families": None,
        "funnel_month": "2026-09",
        "funnel_cutoff_date": "2026-09-30",
        "marketing_access": ACCESS,
    }


class _FreezeSession:
    def __init__(self, read_session):
        self.read_session = read_session
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    @property
    def no_autoflush(self):
        return self.read_session.no_autoflush

    def query(self, *args, **kwargs):
        return self.read_session.query(*args, **kwargs)

    def add(self, value):
        self.added.append(value)

    def flush(self):
        for value in self.added:
            if isinstance(value, MarketingCampaignV2ORM) and value.id is None:
                value.id = 990

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


@pytest.mark.parametrize("source", SOURCES)
@pytest.mark.parametrize(
    ("mode", "match", "included", "excluded", "matched"),
    MATRIX,
)
def test_m25_matrix_all_sources_preview_detail_and_recipients(
    monkeypatch,
    m25_history_session,
    source,
    mode,
    match,
    included,
    excluded,
    matched,
):
    _install_source(monkeypatch, source)
    kwargs = _kwargs(source, _rule(mode, match))

    preview = audience.build_campaign_v2_audience_preview(
        **kwargs,
        session=m25_history_session,
    )
    included_detail = audience.build_campaign_v2_audience_preview_detail(
        bucket="HISTORY_INCLUDED",
        page=1,
        page_size=50,
        **kwargs,
        session=m25_history_session,
    )
    excluded_detail = audience.build_campaign_v2_audience_preview_detail(
        bucket="HISTORY_EXCLUDED",
        page=1,
        page_size=50,
        **kwargs,
        session=m25_history_session,
    )
    recipients = audience.build_campaign_v2_audience_preview_detail(
        bucket="RECIPIENTS",
        page=1,
        page_size=50,
        **kwargs,
        session=m25_history_session,
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

    assert {
        row["phone_mx10"] for row in included_detail["rows"]
    } == {PHONES[key] for key in included}
    assert {
        row["phone_mx10"] for row in excluded_detail["rows"]
    } == {PHONES[key] for key in excluded}
    assert {
        row["phone_mx10"] for row in recipients["rows"]
    } == {PHONES[key] for key in included}

    decisions = {
        row["phone_mx10"]: row
        for row in (*included_detail["rows"], *excluded_detail["rows"])
    }
    assert decisions[PHONES["D"]]["history_matched"] is False
    assert decisions[PHONES["D"]]["history_reasons"] == []
    assert set(decisions[PHONES["C"]]["history_reasons"]) == {
        "HISTORY_DELIVERY_VIEWED",
        "HISTORY_BUTTON_INTERACTION",
    }

    assert preview["filters"]["historical_targeting"] == _rule(mode, match)
    assert "history_exclusion" not in preview["filters"]

    if source == audience.SOURCE_EXPIRED_MEMBERS:
        assert preview["filters"]["expiration_date_from"] == "2026-08-01"
        assert preview["filters"]["expiration_date_to"] == "2026-08-31"
        assert preview["filters"]["audience_families"] == ["DOMICILIADO"]
    elif source == audience.SOURCE_ACTIVE_MEMBERS:
        assert "expiration_date_from" not in preview["filters"]
        assert "expiration_date_to" not in preview["filters"]
        assert preview["filters"]["audience_families"] == ["DOMICILIADO"]
    else:
        assert preview["filters"]["funnel_month"] == "2026-09"
        assert preview["filters"]["funnel_cutoff_date"] == "2026-09-30"
        assert "audience_families" not in preview["filters"]
        assert "expiration_date_from" not in preview["filters"]
        assert "expiration_date_to" not in preview["filters"]


def test_m25_expired_history_then_dedupe_preserves_source_filters(
    monkeypatch,
    m25_history_session,
):
    _install_source(
        monkeypatch,
        audience.SOURCE_EXPIRED_MEMBERS,
        duplicate_c=True,
    )
    kwargs = _kwargs(
        audience.SOURCE_EXPIRED_MEMBERS,
        _rule("INCLUDE", "ALL"),
    )

    preview = audience.build_campaign_v2_audience_preview(
        **kwargs,
        session=m25_history_session,
    )
    recipients = audience.build_campaign_v2_audience_preview_detail(
        bucket="RECIPIENTS",
        page=1,
        page_size=50,
        **kwargs,
        session=m25_history_session,
    )

    assert preview["before_history_filter_count"] == 4
    assert preview["history_included_count"] == 1
    assert preview["duplicate_count"] == 1
    assert preview["unique_recipient_count"] == 1
    assert [row["phone_mx10"] for row in recipients["rows"]] == [PHONES["C"]]


def test_m25_mixed_conditions_are_atomic_on_active_members(
    monkeypatch,
    m25_history_session,
):
    _install_source(monkeypatch, audience.SOURCE_ACTIVE_MEMBERS)

    all_preview = audience.build_campaign_v2_audience_preview(
        **_kwargs(
            audience.SOURCE_ACTIVE_MEMBERS,
            _rule("INCLUDE", "ALL", mixed=True),
        ),
        session=m25_history_session,
    )
    any_preview = audience.build_campaign_v2_audience_preview(
        **_kwargs(
            audience.SOURCE_ACTIVE_MEMBERS,
            _rule("INCLUDE", "ANY", mixed=True),
        ),
        session=m25_history_session,
    )

    assert all_preview["unique_recipient_count"] == 1
    assert any_preview["unique_recipient_count"] == 3
    assert all_preview["matched_by_delivery_bucket"] == {"VIEWED": 1}
    assert all_preview["matched_by_outcome"] == {"SUCCESSFUL": 1}
    assert all_preview["matched_by_button_interaction"] == 1


@pytest.mark.parametrize("source", SOURCES)
def test_m25_preview_freeze_stable_for_every_source(
    monkeypatch,
    m25_history_session,
    source,
):
    _install_source(monkeypatch, source)
    kwargs = _kwargs(source, _rule("INCLUDE", "ANY"))

    first = creation.build_campaign_v2_freeze_preview(
        **kwargs,
        session=m25_history_session,
    )
    second = creation.build_campaign_v2_freeze_preview(
        **kwargs,
        session=m25_history_session,
    )
    assert first["preview_fingerprint"] == second["preview_fingerprint"]

    write_session = _FreezeSession(m25_history_session)
    frozen = creation.freeze_campaign_v2(
        name=f"M25 {source}",
        purpose=(
            "NEW_SALE"
            if source == audience.SOURCE_FUNNEL_PORTFOLIO
            else "REACTIVATION"
        ),
        expected_preview_fingerprint=first["preview_fingerprint"],
        created_by_user_id=7,
        now=BASE + timedelta(days=1),
        **kwargs,
        session=write_session,
    )

    assert frozen["recipient_count"] == 3
    assert write_session.commits == 1
    campaign = write_session.added[0]
    filters = campaign.audience_definition_json["filters"]
    assert filters["historical_targeting"] == _rule("INCLUDE", "ANY")
    assert "history_exclusion" not in filters
    evaluation = campaign.audience_definition_json["source_metadata"][
        "history_evaluation"
    ]
    assert evaluation["observed_before"] is not None
    assert evaluation["observed_after"] is None


def test_m25_new_relevant_evidence_causes_preview_mismatch(
    monkeypatch,
    m25_history_session,
):
    source = audience.SOURCE_ACTIVE_MEMBERS
    _install_source(monkeypatch, source)
    kwargs = _kwargs(source, _rule("INCLUDE", "ANY"))

    preview = creation.build_campaign_v2_freeze_preview(
        **kwargs,
        session=m25_history_session,
    )
    assert preview["unique_recipient_count"] == 3

    m25_history_session.add(_campaign(4, "Campaign NEW EVIDENCE", ["BRANCH A"]))
    m25_history_session.flush()
    new_snapshot = _snapshot(
        m25_history_session,
        4,
        BASE + timedelta(hours=3),
        "4" * 64,
    )
    _obs(
        m25_history_session,
        new_snapshot.id,
        PHONES["D"],
        "SUCCESSFUL",
        "VIEWED",
        [],
    )
    m25_history_session.commit()

    write_session = _FreezeSession(m25_history_session)
    with pytest.raises(creation.MarketingCampaignV2PreviewMismatchError):
        creation.freeze_campaign_v2(
            name="M25 drift",
            purpose="ACTIVE_MEMBERS",
            expected_preview_fingerprint=preview["preview_fingerprint"],
            created_by_user_id=7,
            now=BASE + timedelta(days=1),
            **kwargs,
            session=write_session,
        )

    assert write_session.added == []
    assert write_session.commits == 0


def test_m25_legacy_exclusion_freezes_legacy_shape(
    monkeypatch,
    m25_history_session,
):
    source = audience.SOURCE_EXPIRED_MEMBERS
    _install_source(monkeypatch, source)
    legacy = {
        "delivery_buckets": ["VIEWED"],
        "outcomes": [],
        "button_interacted": True,
        "lookback_days": None,
    }
    kwargs = {
        "source": source,
        "audience_families": ["DOMICILIADO"],
        "allowed_sucursal_keys": ("BRANCH A",),
        "expiration_date_from": "2026-08-01",
        "expiration_date_to": "2026-08-31",
        "history_exclusion": legacy,
    }

    preview = creation.build_campaign_v2_freeze_preview(
        **kwargs,
        session=m25_history_session,
    )
    detail = audience.build_campaign_v2_audience_preview_detail(
        bucket="HISTORY_EXCLUDED",
        page=1,
        page_size=50,
        **kwargs,
        session=m25_history_session,
    )

    assert preview["unique_recipient_count"] == 1
    assert preview["filters"]["history_exclusion"] == legacy
    assert "historical_targeting" not in preview["filters"]
    assert preview["excluded_by_delivery_bucket"] == {"VIEWED": 2}
    assert preview["excluded_by_button_interaction"] == 2
    assert all("history_exclusion_reasons" in row for row in detail["rows"])

    write_session = _FreezeSession(m25_history_session)
    frozen = creation.freeze_campaign_v2(
        name="M25 legacy",
        purpose="REACTIVATION",
        expected_preview_fingerprint=preview["preview_fingerprint"],
        created_by_user_id=7,
        now=BASE + timedelta(days=1),
        **kwargs,
        session=write_session,
    )
    assert frozen["recipient_count"] == 1
    filters = write_session.added[0].audience_definition_json["filters"]
    assert filters["history_exclusion"] == legacy
    assert "historical_targeting" not in filters


def test_m25_provider_boundary_uses_persisted_m13_only():
    evaluator_source = inspect.getsource(audience._evaluate_historical_targeting)
    history_source = inspect.getsource(provider_history.get_provider_history_for_phones)

    assert "get_provider_history_for_phones" in evaluator_source
    assert "ProviderRecipientObservationORM" in history_source
    assert "ProviderStatsSnapshotORM" in history_source

    forbidden = (
        "requests.",
        "httpx",
        "/v2/broadcast",
        "capture_campaign_v2_provider_stats_snapshot",
        "refresh",
    )
    for token in forbidden:
        assert token not in evaluator_source
        assert token not in history_source
