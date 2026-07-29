from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

import app.services.marketing_dashboard_service as service
from app.services.marketing_access import MarketingAccess
from app.services.marketing_attribution import (
    SaleRecord,
    VisitEvent,
)


def _global_access() -> MarketingAccess:
    return MarketingAccess(
        type="GLOBAL",
        is_global=True,
        branch_ids=(),
        role="ADMIN",
        can_edit_inputs=True,
    )


def test_dashboard_builds_branch_and_summary_metrics(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        service,
        "_load_available_branches",
        lambda: [
            service.MarketingBranch(1, "Sucursal A", 1),
            service.MarketingBranch(2, "Sucursal B", 2),
        ],
    )
    monkeypatch.setattr(
        service,
        "_load_inputs_by_branch",
        lambda **_: {
            1: SimpleNamespace(
                investment=Decimal("100.00"),
                leads=10,
            )
        },
    )
    monkeypatch.setattr(
        service,
        "_load_visit_events",
        lambda **_: service.VisitLoadResult(
            events=[
                VisitEvent(
                    "visit-a-1",
                    1,
                    date(2026, 7, 1),
                    "0000000000",
                    "PASE 2 DIAS GRATIS",
                ),
                VisitEvent(
                    "visit-a-2",
                    1,
                    date(2026, 7, 2),
                    "0000000000",
                    "PASE RECORRIDO",
                ),
                VisitEvent(
                    "visit-b-1",
                    2,
                    date(2026, 7, 3),
                    "1111111111",
                    "PASE RECORRIDO",
                ),
            ],
            eligible_visit_events=4,
            visit_events_with_valid_phone=3,
            visit_events_without_valid_phone=1,
            snapshot_id=50,
        ),
    )
    monkeypatch.setattr(
        service,
        "_load_sales",
        lambda **_: service.SalesLoadResult(
            sales=[
                SaleRecord(
                    "id_socio:member-1",
                    1,
                    date(2026, 7, 3),
                    "0000000000",
                    "member-1",
                    Decimal("250.00"),
                )
            ],
            snapshot_ids=[60],
        ),
    )

    result = service.build_marketing_dashboard(
        month="2026-07",
        access=_global_access(),
        today=date(2026, 8, 30),
    )

    assert result["cohort_mode"] == "visit_month"
    assert result["scope"]["branch_ids"] == [1, 2]
    assert result["summary"]["investment"] == 100.0
    assert result["summary"]["leads"] == 10
    assert result["summary"]["visits"] == 2
    assert result["summary"]["sales"] == 1
    assert result["summary"]["sales_revenue"] == 250.0
    assert result["summary"]["lead_to_visit_rate"] == 0.2
    assert result["summary"]["visit_to_sale_rate"] == 0.5
    assert result["branches"][0]["visits"] == 1
    assert result["data_quality"]["eligible_visit_events"] == 4
    assert (
        result["data_quality"]["visit_phone_coverage_rate"]
        == 0.75
    )
    assert result["data_quality"]["cohort_complete"] is True


def test_dashboard_zero_denominators_are_null(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        service,
        "_load_available_branches",
        lambda: [
            service.MarketingBranch(1, "Sucursal A", 1)
        ],
    )
    monkeypatch.setattr(
        service,
        "_load_inputs_by_branch",
        lambda **_: {},
    )
    monkeypatch.setattr(
        service,
        "_load_visit_events",
        lambda **_: service.VisitLoadResult(),
    )
    monkeypatch.setattr(
        service,
        "_load_sales",
        lambda **_: service.SalesLoadResult(),
    )

    result = service.build_marketing_dashboard(
        month="2026-07",
        access=_global_access(),
        today=date(2026, 7, 15),
    )

    summary = result["summary"]
    assert summary["cost_per_lead"] is None
    assert summary["cost_per_visit"] is None
    assert summary["cost_per_sale"] is None
    assert summary["lead_to_visit_rate"] is None
    assert summary["visit_to_sale_rate"] is None
    assert summary["lead_to_sale_rate"] is None
    assert (
        result["data_quality"]["visit_phone_coverage_rate"]
        is None
    )
    assert result["data_quality"]["cohort_complete"] is False


def test_sales_window_can_intersect_three_calendar_months():
    assert service._calendar_month_starts(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 2),
    ) == [
        date(2026, 1, 1),
        date(2026, 2, 1),
        date(2026, 3, 1),
    ]
