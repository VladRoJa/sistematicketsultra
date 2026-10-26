from __future__ import annotations

from datetime import date
from io import BytesIO
from zipfile import ZipFile

import pytest

from app.services.marketing_sales_funnel_weekly_export_service import (
    closed_business_date,
    create_workbook,
    find_weekly_cutoffs,
    scopes_from_access,
)


def test_monday_becomes_available_only_on_tuesday_if_canonical():
    calls = []

    def available(first_of_month):
        calls.append(first_of_month)
        return [
            date(2026, 10, 12), date(2026, 10, 19),
            date(2026, 10, 26), date(2026, 10, 27),
        ]

    assert closed_business_date(date(2026, 10, 26)) == date(2026, 10, 25)
    assert find_weekly_cutoffs(
        date(2026, 10, 26), available,
        first_month=date(2026, 10, 1),
        today=date(2026, 10, 26),
    ) == [date(2026, 10, 12), date(2026, 10, 19)]
    assert find_weekly_cutoffs(
        date(2026, 10, 26), available,
        first_month=date(2026, 10, 1),
        today=date(2026, 10, 27),
    ) == [date(2026, 10, 12), date(2026, 10, 19), date(2026, 10, 26)]
    assert calls == [date(2026, 10, 1)] * 2


def test_no_fallback_and_no_tuesday_in_weekly_dates():
    assert find_weekly_cutoffs(
        date(2026, 10, 20),
        lambda _: [date(2026, 10, 6), date(2026, 10, 13), date(2026, 10, 19)],
        first_month=date(2026, 10, 1),
        today=date(2026, 10, 22),
    ) == [date(2026, 10, 19)]


def test_empty_dates_do_not_create_fake_cuts():
    assert find_weekly_cutoffs(
        date(2026, 10, 19),
        lambda _: [],
        first_month=date(2026, 9, 1),
        today=date(2026, 10, 20),
    ) == []


def _branch(bid, name, leads, visits, digital):
    return {
        "sucursal_id": bid, "sucursal": name,
        "leads_meta": leads, "visits_total": visits, "sales_digital": digital,
        "sales_digital_organic": 1, "sales_web": 0, "sales_btl": 1,
        "sales_total": digital + 2, "investment": 200.0,
        "revenue_digital": 100.0, "revenue_web": 0,
        "revenue_btl": 50.0, "revenue_total": 150.0,
    }


OPTIONS = [
    {"sucursal_id": 1, "sucursal": "Club Uno", "region_id": 8, "region": "Mexicali"},
    {"sucursal_id": 2, "sucursal": "Club Dos", "region_id": 8, "region": "Mexicali"},
]


def _snapshot(day, first=(100, 10, 6), second=(100, 30, 6)):
    return {
        "selected_cutoff_date": day,
        "branches": [
            _branch(1, "Club Uno", *first),
            _branch(2, "Club Dos", *second),
        ],
    }


def test_authorized_scope_catalog_has_only_authorized_branches():
    options, by_id = scopes_from_access(OPTIONS[:1], False)
    assert by_id == {1: ("R:8", "S:1")}
    assert options == [
        ("Todas las autorizadas", "ALL"),
        ("Región | Mexicali", "R:8"),
        ("Sucursal | Club Uno", "S:1"),
    ]


def test_generates_xlsx_with_two_disconnected_monthly_series_and_selectors():
    data = create_workbook(
        _snapshot("2026-10-19"),
        [_snapshot("2026-09-21"), _snapshot("2026-10-12"),
         _snapshot("2026-10-19")],
        OPTIONS,
        is_global=True,
    )
    assert data[:2] == b"PK"
    with ZipFile(BytesIO(data)) as z:
        parts = z.namelist()
        assert "xl/charts/chart1.xml" in parts
        workbook = z.read("xl/workbook.xml").decode()
        assert "Resumen" in workbook
        assert "Detalle diario" in workbook
        assert "Lun 2026-09-21" in workbook
        assert "Lun 2026-10-19" in workbook
        assert "FunnelAmbitos" in workbook
        assert "FunnelMeses" in workbook
        chart = z.read("xl/charts/chart1.xml").decode()
        # 3 indicadores * 2 meses: no existe una serie que abarque ambos meses.
        assert chart.count("<c:ser>") == 6
        trend = z.read("xl/worksheets/sheet3.xml").decode()
        assert "SUMIFS" in trend
        assert "2026-09" in trend
        assert "2026-10" in trend
        assert "Comparar las tres" in trend


def test_empty_history_still_preserves_daily_export():
    data = create_workbook(
        _snapshot("2026-10-19"), [], OPTIONS, is_global=False
    )
    with ZipFile(BytesIO(data)) as z:
        assert "xl/charts/chart1.xml" not in z.namelist()
        text = z.read("xl/sharedStrings.xml").decode()
        assert "Sin lunes completos" in text
        assert "Todas las autorizadas" in text


@pytest.mark.parametrize("is_global,label", [
    (False, "Todas las autorizadas"),
    (True, "Todo Ultra"),
])
def test_scopes_expose_correct_general_label(is_global, label):
    options, _ = scopes_from_access(OPTIONS, is_global)
    assert options[0] == (label, "ALL")
