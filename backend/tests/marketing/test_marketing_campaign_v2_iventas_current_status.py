from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.services import marketing_campaign_iventas_followup_service as followup
from app.services import marketing_campaign_v2_audience_service as audience


@pytest.fixture(autouse=True)
def _empty_blacklist(monkeypatch):
    monkeypatch.setattr(audience, "get_blacklisted_phones", lambda **_kwargs: set())


def _candidate(phone: str):
    return audience.MarketingCampaignV2AudienceCandidate(
        source=audience.SOURCE_FUNNEL_PORTFOLIO,
        source_ref_type="FUNNEL_CONTACT",
        source_ref_id=None,
        phone_raw=phone,
        phone_mx10=phone,
    )


def test_current_iventas_status_filter_keeps_viewed_without_campaign_history(monkeypatch):
    rows = (
        _candidate("6861111111"),
        _candidate("6862222222"),
        _candidate("6863333333"),
    )

    monkeypatch.setattr(
        audience,
        "get_latest_iventas_status_by_phone",
        lambda **_kwargs: {
            "sync_run_ids": [71, 77],
            "period_keys": ["IVENTAS-2026-07", "IVENTAS-2026-10"],
            "statuses": {
                "6861111111": "VIEWED",
                "6862222222": "DELIVERED",
                "6863333333": None,
            },
        },
    )

    kept, metadata = audience._filter_by_iventas_current_status(
        candidates=rows,
        selected_statuses=("VIEWED",),
        session=object(),
    )

    assert [row.phone_mx10 for row in kept] == ["6861111111"]
    assert metadata["sync_run_ids"] == [71, 77]
    assert metadata["period_keys"] == ["IVENTAS-2026-07", "IVENTAS-2026-10"]
    assert metadata["before_phone_count"] == 3
    assert metadata["matched_phone_count"] == 1
    assert metadata["status_counts"]["VIEWED"] == 1
    assert metadata["status_counts"]["DELIVERED"] == 1
    assert metadata["status_counts"]["NO_DATA"] == 1


def test_current_iventas_status_filter_supports_no_data(monkeypatch):
    rows = (
        _candidate("6861111111"),
        _candidate("6862222222"),
    )

    monkeypatch.setattr(
        audience,
        "get_latest_iventas_status_by_phone",
        lambda **_kwargs: {
            "sync_run_ids": [78],
            "period_keys": ["IVENTAS-2026-10"],
            "statuses": {
                "6861111111": "FAILED",
                "6862222222": None,
            },
        },
    )

    kept, _metadata = audience._filter_by_iventas_current_status(
        candidates=rows,
        selected_statuses=("NO_DATA",),
        session=object(),
    )

    assert [row.phone_mx10 for row in kept] == ["6862222222"]


def test_current_iventas_status_filter_rejects_unknown_status():
    try:
        audience._normalize_iventas_current_statuses(["READ"])
    except audience.MarketingCampaignV2AudienceValidationError as exc:
        assert "READ" in str(exc)
    else:
        raise AssertionError("Expected unsupported iVentas status to be rejected")


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def join(self, *_args, **_kwargs):
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def query(self, *_args, **_kwargs):
        return _FakeQuery(self._rows)


def _run(run_id: int, period_key: str, date_to_value: date):
    return SimpleNamespace(
        id=run_id,
        period_key=period_key,
        date_from=date(date_to_value.year, date_to_value.month, 1),
        date_to=date_to_value,
        finished_at=datetime(
            date_to_value.year,
            date_to_value.month,
            date_to_value.day,
            20,
            0,
            tzinfo=timezone.utc,
        ),
    )


def _contact(
    contact_id: int,
    phone: str,
    status: str,
    *,
    last_outbound: datetime | None = None,
):
    return SimpleNamespace(
        id=contact_id,
        phone_mx10=phone,
        last_message_status=status,
        last_outbound_message_at_utc=last_outbound,
        first_message_at_utc=None,
        created_at_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_latest_iventas_status_resolves_each_phone_across_canonical_months():
    july = _run(71, "IVENTAS-2026-07", date(2026, 7, 31))
    september = _run(91, "IVENTAS-2026-09", date(2026, 9, 30))
    rows = [
        (
            _contact(
                1,
                "6861111111",
                "viewed",
                last_outbound=datetime(2026, 7, 20, tzinfo=timezone.utc),
            ),
            july,
        ),
        (
            _contact(
                2,
                "6861111111",
                "delivered",
                last_outbound=datetime(2026, 9, 10, tzinfo=timezone.utc),
            ),
            september,
        ),
        (
            _contact(
                3,
                "6862222222",
                "viewed",
                last_outbound=datetime(2026, 7, 25, tzinfo=timezone.utc),
            ),
            july,
        ),
    ]

    resolved = followup.get_latest_iventas_status_by_phone(
        phones={"6861111111", "6862222222", "6863333333"},
        session=_FakeSession(rows),
    )

    assert resolved["statuses"] == {
        "6861111111": "DELIVERED",
        "6862222222": "VIEWED",
        "6863333333": None,
    }
    assert resolved["observations"]["6861111111"]["sync_run_id"] == 91
    assert resolved["observations"]["6862222222"]["sync_run_id"] == 71
    assert resolved["observations"]["6863333333"] is None
    assert resolved["sync_run_ids"] == [71, 91]
    assert resolved["period_keys"] == [
        "IVENTAS-2026-07",
        "IVENTAS-2026-09",
    ]


def _source_candidate(source: str, phone: str):
    return audience.MarketingCampaignV2AudienceCandidate(
        source=source,
        source_ref_type="TEST",
        source_ref_id=None,
        phone_raw=phone,
        phone_mx10=phone,
        tarifa_raw="TARIFA TEST",
        sucursal="SUCURSAL TEST",
        sucursal_key="SUCURSAL_TEST",
    )


def _mock_current_statuses(monkeypatch):
    monkeypatch.setattr(
        audience,
        "get_latest_iventas_status_by_phone",
        lambda **_kwargs: {
            "sync_run_ids": [71, 91],
            "period_keys": ["IVENTAS-2026-07", "IVENTAS-2026-09"],
            "statuses": {
                "6861111111": "VIEWED",
                "6862222222": "DELIVERED",
            },
        },
    )


def test_current_iventas_status_applies_to_active_members(monkeypatch):
    _mock_current_statuses(monkeypatch)
    monkeypatch.setattr(
        audience,
        "_load_active_source",
        lambda **_kwargs: audience._SourceLoadResult(
            universe_count=2,
            scoped_count=2,
            candidates=(
                _source_candidate(audience.SOURCE_ACTIVE_MEMBERS, "6861111111"),
                _source_candidate(audience.SOURCE_ACTIVE_MEMBERS, "6862222222"),
            ),
            current_status_blocked=(),
            current_status_counts={},
            metadata={},
        ),
    )
    monkeypatch.setattr(
        audience,
        "_read_v2_tariff_catalog",
        lambda **_kwargs: {
            "TARIFA TEST": ("TEST", "DOMICILIADO"),
        },
    )

    plan = audience._build_campaign_v2_audience_plan(
        source=audience.SOURCE_ACTIVE_MEMBERS,
        audience_families=["DOMICILIADO"],
        allowed_sucursal_keys=None,
        expiration_date_from=None,
        expiration_date_to=None,
        iventas_current_statuses=["VIEWED"],
        session=object(),
    )

    assert [row.phone_mx10 for row in plan.recipients] == ["6861111111"]
    assert plan.filters["iventas_current_statuses"] == ["VIEWED"]


def test_current_iventas_status_applies_to_expired_members(monkeypatch):
    _mock_current_statuses(monkeypatch)
    monkeypatch.setattr(
        audience,
        "_load_expired_source",
        lambda **_kwargs: audience._SourceLoadResult(
            universe_count=2,
            scoped_count=2,
            candidates=(
                _source_candidate(audience.SOURCE_EXPIRED_MEMBERS, "6861111111"),
                _source_candidate(audience.SOURCE_EXPIRED_MEMBERS, "6862222222"),
            ),
            current_status_blocked=(),
            current_status_counts={},
            metadata={},
        ),
    )
    monkeypatch.setattr(
        audience,
        "_read_v2_tariff_catalog",
        lambda **_kwargs: {
            "TARIFA TEST": ("TEST", "DOMICILIADO"),
        },
    )

    plan = audience._build_campaign_v2_audience_plan(
        source=audience.SOURCE_EXPIRED_MEMBERS,
        audience_families=["DOMICILIADO"],
        allowed_sucursal_keys=None,
        expiration_date_from="2026-07-01",
        expiration_date_to="2026-07-31",
        iventas_current_statuses=["VIEWED"],
        session=object(),
    )

    assert [row.phone_mx10 for row in plan.recipients] == ["6861111111"]
    assert plan.filters["iventas_current_statuses"] == ["VIEWED"]


def test_current_iventas_status_applies_to_funnel_portfolio(monkeypatch):
    _mock_current_statuses(monkeypatch)
    candidate_viewed = audience.funnel_source.MarketingCampaignV2FunnelCandidate(
        phone_raw="6861111111",
        phone_mx10="6861111111",
        contact_id="1",
        sucursal_id=1,
        sucursal_key="SUCURSAL_TEST",
        channel="WHATSAPP",
        source_date="2026-07-10",
        origin="META_AD",
        source_reference="lead-1",
    )
    candidate_delivered = audience.funnel_source.MarketingCampaignV2FunnelCandidate(
        phone_raw="6862222222",
        phone_mx10="6862222222",
        contact_id="2",
        sucursal_id=1,
        sucursal_key="SUCURSAL_TEST",
        channel="WHATSAPP",
        source_date="2026-07-11",
        origin="META_AD",
        source_reference="lead-2",
    )
    monkeypatch.setattr(
        audience.funnel_source,
        "load_campaign_v2_funnel_source",
        lambda **_kwargs: audience.funnel_source.MarketingCampaignV2FunnelSourceResult(
            funnel_month="2026-07",
            funnel_cutoff_date="2026-07-31",
            universe_count=2,
            scoped_count=2,
            funnel_candidates=(candidate_viewed, candidate_delivered),
            buyer_excluded=(),
            invalid_phone=(),
            active_member_suppressed=(),
            candidates=(candidate_viewed, candidate_delivered),
            metadata={},
        ),
    )

    plan = audience._build_campaign_v2_audience_plan(
        source=audience.SOURCE_FUNNEL_PORTFOLIO,
        audience_families=None,
        allowed_sucursal_keys=None,
        expiration_date_from=None,
        expiration_date_to=None,
        iventas_current_statuses=["VIEWED"],
        funnel_month="2026-07",
        funnel_cutoff_date="2026-07-31",
        marketing_access=object(),
        session=object(),
    )

    assert [row.phone_mx10 for row in plan.recipients] == ["6861111111"]
    assert plan.filters["iventas_current_statuses"] == ["VIEWED"]
