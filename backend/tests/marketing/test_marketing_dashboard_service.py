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
def test_attribution_detail_serializes_reconciled_sales(
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
        "_load_visit_events",
        lambda **_: service.VisitLoadResult(
            events=[
                VisitEvent(
                    "visit-a",
                    1,
                    date(2026, 7, 1),
                    "0000000000",
                    "PASE 2 DIAS GRATIS",
                ),
                VisitEvent(
                    "visit-b",
                    2,
                    date(2026, 7, 10),
                    "1111111111",
                    "PASE RECORRIDO",
                ),
            ],
            snapshot_id=50,
        ),
    )
    monkeypatch.setattr(
        service,
        "_load_sales",
        lambda **_: service.SalesLoadResult(
            sales=[
                SaleRecord(
                    sale_key="id_socio:member-1",
                    branch_id=1,
                    payment_date=date(2026, 7, 3),
                    phone="0000000000",
                    member_id="member-1",
                    revenue=Decimal("250.00"),
                    snapshot_id=60,
                    source_row_id=6001,
                    folio="F-1",
                    member_name="Socio Uno",
                    membership_type="MENSUAL",
                    tariff="TARIFA A",
                    registration="NUEVO",
                    pass_name="PASE 2 DIAS GRATIS",
                    payment_place="CAJA",
                    listed_total=Decimal("250.00"),
                ),
                SaleRecord(
                    sale_key="id_socio:member-2",
                    branch_id=2,
                    payment_date=date(2026, 7, 12),
                    phone="1111111111",
                    member_id="member-2",
                    revenue=Decimal("0.00"),
                    snapshot_id=61,
                    source_row_id=6101,
                    folio="F-2",
                    member_name="Socio Dos",
                    membership_type="MENSUAL",
                    tariff="CORTESIA",
                    registration=None,
                    pass_name="PASE RECORRIDO",
                    payment_place="CAJA",
                    listed_total=Decimal("0.00"),
                ),
            ],
            snapshot_ids=[60, 61],
        ),
    )

    result = service.build_marketing_attribution_detail(
        month="2026-07",
        access=_global_access(),
    )

    assert result["summary"] == {
        "sales": 2,
        "sales_revenue": 250.0,
        "review_sales": 1,
        "non_positive_sales": 1,
        "family_plan_additional_members": 0,
    }
    assert result["source"] == {
        "visit_snapshot_id": 50,
        "sales_snapshot_ids": [60, 61],
    }
    assert len(result["rows"]) == 2

    first_row = result["rows"][0]
    assert first_row["sucursal"] == "Sucursal A"
    assert first_row["id_socio"] == "member-1"
    assert first_row["id_folio"] == "F-1"
    assert first_row["socio"] == "Socio Uno"
    assert first_row["telefono"] == "*** *** 0000"
    assert first_row["fecha_visita"] == "2026-07-01"
    assert first_row["fecha_pago"] == "2026-07-03"
    assert first_row["dias_a_venta"] == 2
    assert first_row["tipo_membresia"] == "MENSUAL"
    assert first_row["tarifa"] == "TARIFA A"
    assert first_row["total_pagado"] == 250.0
    assert (
        first_row["attribution_classification"]
        == service.ATTRIBUTION_CLASS_STANDARD
    )
    assert (
        first_row["amount_assigned_to_primary_member"]
        is False
    )
    assert first_row["venta_sin_ingreso_positivo"] is False

    second_row = result["rows"][1]
    assert second_row["total_pagado"] == 0.0
    assert (
        second_row["attribution_classification"]
        == service.ATTRIBUTION_CLASS_REVIEW
    )
    assert (
        second_row["amount_assigned_to_primary_member"]
        is False
    )
    assert second_row["venta_sin_ingreso_positivo"] is True



def test_family_plan_additional_member_is_not_a_review_case(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        service,
        "_load_available_branches",
        lambda: [
            service.MarketingBranch(
                1,
                "Sucursal A",
                1,
            ),
        ],
    )

    monkeypatch.setattr(
        service,
        "_load_visit_events",
        lambda **_: service.VisitLoadResult(
            events=[
                VisitEvent(
                    "visit-family",
                    1,
                    date(2026, 7, 23),
                    "0000000000",
                    "PASE RECORRIDO",
                ),
            ],
            snapshot_id=50,
        ),
    )

    monkeypatch.setattr(
        service,
        "_load_sales",
        lambda **_: service.SalesLoadResult(
            sales=[
                SaleRecord(
                    sale_key="id_socio:family-member",
                    branch_id=1,
                    payment_date=date(2026, 7, 24),
                    phone="0000000000",
                    member_id="family-member",
                    revenue=Decimal("0.00"),
                    snapshot_id=60,
                    source_row_id=6001,
                    folio="F-FAMILY",
                    member_name="Socio Adicional",
                    membership_type="Sin contrato",
                    tariff=(
                        "DOMICILIADO 12 MESES "
                        "PLAN FAMILIAR $999 "
                        "(ADULTO + ADULTO)"
                    ),
                    registration=None,
                    pass_name="PASE RECORRIDO",
                    payment_place="Sucursal",
                    listed_total=Decimal("0.00"),
                ),
            ],
            snapshot_ids=[60],
        ),
    )

    result = service.build_marketing_attribution_detail(
        month="2026-07",
        access=_global_access(),
    )

    assert result["summary"] == {
        "sales": 1,
        "sales_revenue": 0.0,
        "review_sales": 0,
        "non_positive_sales": 0,
        "family_plan_additional_members": 1,
    }

    assert len(result["rows"]) == 1

    row = result["rows"][0]

    assert (
        row["attribution_classification"]
        == service.ATTRIBUTION_CLASS_FAMILY_ADDITIONAL
    )
    assert (
        row["amount_assigned_to_primary_member"]
        is True
    )
    assert row["venta_sin_ingreso_positivo"] is False
    assert row["total"] == 0.0
    assert row["total_pagado"] == 0.0

def test_attribution_detail_rejects_branch_outside_scope(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        service,
        "_load_available_branches",
        lambda: [
            service.MarketingBranch(1, "Sucursal A", 1),
        ],
    )

    with pytest.raises(
        service.MarketingAuthorizationError,
        match="fuera del alcance autorizado",
    ):
        service.build_marketing_attribution_detail(
            month="2026-07",
            access=_global_access(),
            sucursal_id=999,
        )
