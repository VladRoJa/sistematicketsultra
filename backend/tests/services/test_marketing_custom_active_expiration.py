from datetime import date, datetime, timezone
from types import SimpleNamespace as NS

import pytest

from app.services import marketing_campaign_audience_service as audience
from app.services import marketing_reactivation_service as service


NOW = datetime(2026, 9, 9, 18, tzinfo=timezone.utc)


def _plan(rows):
    return {
        "sources": {},
        "summary": {"eligible": len(rows)},
        "eligible_rows": rows,
    }


def _active_row(phone: str, expiration: str | None):
    return {
        "phone_mx10": phone,
        "fecha_vencimiento": expiration,
    }


def test_custom_active_filters_by_expiration_dates(monkeypatch):
    monkeypatch.setattr(audience, "exported_counts", lambda *args, **kwargs: {})

    result = audience.prepare_v1_plan(
        filters={
            "campaign_type": "PERSONALIZADA",
            "universo": "ACTIVOS",
            "fecha_desde": "2026-09-10",
            "fecha_hasta": "2026-09-15",
        },
        allowed_sucursal_keys=None,
        session=None,
        now=NOW,
        active_builder=lambda **kwargs: _plan([
            _active_row("6861000001", "2026-09-09"),
            _active_row("6861000002", "2026-09-10"),
            _active_row("6861000003", "2026-09-15"),
            _active_row("6861000004", "2026-09-16"),
            _active_row("6861000005", None),
        ]),
        expired_builder=None,
    )

    assert [row["phone_mx10"] for row in result["eligible_rows"]] == [
        "6861000002",
        "6861000003",
    ]
    assert result["summary"]["eligible"] == 2


def test_custom_active_allows_open_date_range(monkeypatch):
    monkeypatch.setattr(audience, "exported_counts", lambda *args, **kwargs: {})

    result = audience.prepare_v1_plan(
        filters={
            "campaign_type": "PERSONALIZADA",
            "universo": "ACTIVOS",
            "fecha_desde": "2026-09-10",
        },
        allowed_sucursal_keys=None,
        session=None,
        now=NOW,
        active_builder=lambda **kwargs: _plan([
            _active_row("6861000001", "2026-09-09"),
            _active_row("6861000002", "2026-09-10"),
            _active_row("6861000003", "2026-10-01"),
        ]),
        expired_builder=None,
    )

    assert [row["phone_mx10"] for row in result["eligible_rows"]] == [
        "6861000002",
        "6861000003",
    ]


def test_custom_active_rejects_inverted_dates():
    with pytest.raises(
        service.MarketingReactivationValidationError,
        match="La fecha desde no puede ser posterior",
    ):
        audience.prepare_v1_plan(
            filters={
                "campaign_type": "PERSONALIZADA",
                "universo": "ACTIVOS",
                "fecha_desde": "2026-09-20",
                "fecha_hasta": "2026-09-10",
            },
            allowed_sucursal_keys=None,
            session=None,
            now=NOW,
            active_builder=None,
            expired_builder=None,
        )
