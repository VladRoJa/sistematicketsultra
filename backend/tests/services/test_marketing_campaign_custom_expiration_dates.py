from datetime import date, datetime, timezone
from types import SimpleNamespace as NS

import pytest

from app.services import marketing_campaign_audience_service as audience
from app.services import marketing_reactivation_service as service


NOW = datetime(2026, 9, 8, 18, tzinfo=timezone.utc)


class Query:
    def __init__(self, result):
        self.result = result

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def first(self):
        return self.result


def plan():
    return {"sources": {}, "summary": {"eligible": 0}, "eligible_rows": []}


def session():
    return NS(query=lambda *args: Query(NS(period_key="CANONICAL")))


def test_custom_expired_accepts_closed_date_range(monkeypatch):
    calls = {}
    monkeypatch.setattr(audience, "exported_counts", lambda *a, **k: {})

    def expired(**kwargs):
        calls.update(kwargs)
        return plan()

    filters = {
        "campaign_type": "PERSONALIZADA",
        "universo": "VENCIDOS",
        "modo_vencidos": "FECHAS",
        "fecha_desde": "2026-01-01",
        "fecha_hasta": "2026-03-31",
    }
    audience.prepare_v1_plan(
        filters=filters,
        allowed_sucursal_keys=None,
        session=session(),
        now=NOW,
        active_builder=None,
        expired_builder=expired,
    )

    assert calls["date_from"] == date(2026, 1, 1)
    assert calls["date_to"] == date(2026, 3, 31)


def test_custom_expired_accepts_open_start_date_range(monkeypatch):
    calls = {}
    monkeypatch.setattr(audience, "exported_counts", lambda *a, **k: {})

    def expired(**kwargs):
        calls.update(kwargs)
        return plan()

    audience.prepare_v1_plan(
        filters={
            "campaign_type": "PERSONALIZADA",
            "universo": "VENCIDOS",
            "modo_vencidos": "FECHAS",
            "fecha_hasta": "2025-12-31",
        },
        allowed_sucursal_keys=None,
        session=session(),
        now=NOW,
        active_builder=None,
        expired_builder=expired,
    )

    assert calls["date_from"] == date.min
    assert calls["date_to"] == date(2025, 12, 31)


def test_custom_expired_accepts_open_end_date_range(monkeypatch):
    calls = {}
    monkeypatch.setattr(audience, "exported_counts", lambda *a, **k: {})

    def expired(**kwargs):
        calls.update(kwargs)
        return plan()

    audience.prepare_v1_plan(
        filters={
            "campaign_type": "PERSONALIZADA",
            "universo": "VENCIDOS",
            "modo_vencidos": "FECHAS",
            "fecha_desde": "2026-01-01",
        },
        allowed_sucursal_keys=None,
        session=session(),
        now=NOW,
        active_builder=None,
        expired_builder=expired,
    )

    assert calls["date_from"] == date(2026, 1, 1)
    assert calls["date_to"] == date(2026, 9, 7)


@pytest.mark.parametrize("filters", [
    {
        "campaign_type": "PERSONALIZADA",
        "universo": "VENCIDOS",
        "modo_vencidos": "FECHAS",
    },
    {
        "campaign_type": "PERSONALIZADA",
        "universo": "VENCIDOS",
        "modo_vencidos": "FECHAS",
        "fecha_desde": "2026-04-01",
        "fecha_hasta": "2026-03-01",
    },
    {
        "campaign_type": "PERSONALIZADA",
        "universo": "VENCIDOS",
        "modo_vencidos": "FECHAS",
        "fecha_hasta": "2026-09-08",
    },
    {
        "campaign_type": "PERSONALIZADA",
        "universo": "VENCIDOS",
        "modo_vencidos": "FECHAS",
        "fecha_desde": "no-es-fecha",
    },
    {
        "campaign_type": "PERSONALIZADA",
        "universo": "VENCIDOS",
        "modo_vencidos": "FECHAS",
        "fecha_desde": "2026-01-01",
        "dias_desde": 90,
    },
])
def test_custom_expiration_dates_reject_invalid_filters(monkeypatch, filters):
    monkeypatch.setattr(audience, "exported_counts", lambda *a, **k: {})
    with pytest.raises(service.MarketingReactivationValidationError):
        audience.prepare_v1_plan(
            filters=filters,
            allowed_sucursal_keys=None,
            session=session(),
            now=NOW,
            active_builder=None,
            expired_builder=lambda **kwargs: plan(),
        )
