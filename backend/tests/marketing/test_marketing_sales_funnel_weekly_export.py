from __future__ import annotations

from datetime import date
from io import BytesIO
from zipfile import ZipFile

import pytest

# Cargar el generador puro sin ejecutar app/__init__.py (factory Flask/DB).
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

# Importación aislada: no ejecutar app factory, migraciones ni BD en QA puro.
original_file = (
    Path(__file__).resolve().parents[2]
    / "app/services/marketing_sales_funnel_original_sheet_service.py"
)
original_spec = spec_from_file_location("funnel_original_sheet", original_file)
assert original_spec is not None and original_spec.loader is not None
original_module = module_from_spec(original_spec)
original_spec.loader.exec_module(original_module)
sys.modules["app.services.marketing_sales_funnel_original_sheet_service"] = original_module

SERVICE_FILE = (
    Path(__file__).resolve().parents[2]
    / "app/services/marketing_sales_funnel_weekly_export_service.py"
)
spec = spec_from_file_location("funnel_weekly_export", SERVICE_FILE)
assert spec is not None and spec.loader is not None
module = module_from_spec(spec)
spec.loader.exec_module(module)

closed_business_date = module.closed_business_date
create_workbook = module.create_workbook
find_weekly_cutoffs = module.find_weekly_cutoffs
scopes_from_access = module.scopes_from_access


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
        assert 'name="Octubre 2026"' in workbook
        assert "Detalle diario" not in workbook
        assert "Lun 2026-09-21" not in workbook
        assert workbook.count('state="hidden"') == 2
        assert 'name="Resumen"' in workbook
        assert "FunnelAmbitos" in workbook
        assert "FunnelMeses" in workbook
        chart = z.read("xl/charts/chart1.xml").decode()
        # 3 indicadores * 2 meses: no existe una serie que abarque ambos meses.
        assert chart.count("<c:ser>") == 6
        # No aceptar 0% artificial en meses ajenos ni en métricas ocultas.
        # Las fechas conservan posiciones: septiembre=0; octubre=1,2.
        from xml.etree import ElementTree as ET
        plot = ET.fromstring(chart)
        chart_ns = {"c": "http://schemas.openxmlformats.org/drawingml/2006/chart"}
        series = plot.findall(".//c:lineChart/c:ser", chart_ns)
        cached = [
            {
                int(pt.attrib["idx"]): float(pt.find("c:v", chart_ns).text)
                for pt in ser.findall("c:val/c:numRef/c:numCache/c:pt", chart_ns)
            }
            for ser in series
        ]
        assert [set(item) for item in cached] == [
            {0}, set(), set(), {1, 2}, set(), set(),
        ]
        assert cached[0][0] == pytest.approx(40 / 200)
        assert cached[3][1] == pytest.approx(40 / 200)
        assert plot.find(".//c:plotVisOnly", chart_ns) is None
        trend = z.read("xl/worksheets/sheet3.xml").decode()
        assert "SUMIFS" in trend
        assert "2026-09" in trend
        assert "2026-10" in trend
        assert "Comparar las tres" in trend
        # Regresión Excel es-MX: S3 jamás debe depender de
        # TEXT(...,"yyyy-mm"), que puede devolver "yyyy-08".
        trend_xml = ET.fromstring(trend)
        cells_ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        start_month_formula = trend_xml.find(".//x:c[@r='S3']/x:f", cells_ns)
        start_month_cached = trend_xml.find(".//x:c[@r='S3']/x:v", cells_ns)
        assert start_month_formula is not None
        assert "YEAR(" in start_month_formula.text
        assert "MONTH(" in start_month_formula.text
        assert "RIGHT(" in start_month_formula.text
        assert '"yyyy-mm"' not in start_month_formula.text
        assert '"aaaa-mm"' not in start_month_formula.text
        assert start_month_cached.text == "2026-08"

        summary_xml = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        cutoff_text_formula = summary_xml.find(".//x:c[@r='A8']/x:f", cells_ns)
        cutoff_text_cached = summary_xml.find(".//x:c[@r='A8']/x:v", cells_ns)
        assert "DAY(" in cutoff_text_formula.text
        assert "MONTH(" in cutoff_text_formula.text
        assert "YEAR(" in cutoff_text_formula.text
        assert '"dd mmm yyyy"' not in cutoff_text_formula.text
        assert "19/10/2026" in cutoff_text_cached.text
        assert "0.1" in trend or "0.2" in trend
        original = z.read("xl/worksheets/sheet4.xml").decode()
        for column in ("Sucursal", "Leads", "Ventas digitales",
                       "Costo por venta (CAC)"):
            assert column in z.read("xl/sharedStrings.xml").decode()
        assert "SUM(D" in original
        assert "RESUMEN COMERCIAL" in z.read("xl/sharedStrings.xml").decode()
        assert "Visitas registradas" in z.read("xl/sharedStrings.xml").decode()
        assert "Corte: 2026-10-19" in z.read("xl/sharedStrings.xml").decode()
        assert 'H' in original
        # Cached numerical values, not every formula left at zero.
        from xml.etree import ElementTree as ET
        xml = ET.fromstring(original)
        ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        cached_visit_total = xml.find(".//x:c[@r='C8']/x:v", ns)
        assert cached_visit_total is not None
        assert float(cached_visit_total.text) == 40.0
        # El detalle Original conserva los contadores que devolvió Flask,
        # sin modificar sus visitas según ventas ni otros campos.
        assert float(xml.find(".//x:c[@r='C6']/x:v", ns).text) == 10.0
        assert float(xml.find(".//x:c[@r='C7']/x:v", ns).text) == 30.0



def test_empty_history_still_preserves_daily_export():
    data = create_workbook(
        _snapshot("2026-10-19"), [], OPTIONS, is_global=False
    )
    with ZipFile(BytesIO(data)) as z:
        assert "xl/charts/chart1.xml" not in z.namelist()
        text = z.read("xl/sharedStrings.xml").decode()
        assert "Sin lunes completos" in text
        assert "Todas las autorizadas" in text
        assert "RESUMEN COMERCIAL" in text
        assert 'name="Octubre 2026"' in z.read("xl/workbook.xml").decode()


@pytest.mark.parametrize("is_global,label", [
    (False, "Todas las autorizadas"),
    (True, "Todo Ultra"),
])
def test_scopes_expose_correct_general_label(is_global, label):
    options, _ = scopes_from_access(OPTIONS, is_global)
    assert options[0] == (label, "ALL")
