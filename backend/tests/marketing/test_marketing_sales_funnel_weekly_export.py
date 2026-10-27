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
        # Etiquetas de porcentaje activadas de fábrica en todas las series.
        labels = plot.findall(".//c:lineChart/c:ser/c:dLbls", chart_ns)
        assert len(labels) == 6
        for element in labels:
            assert element.find("c:showVal", chart_ns).get("val") == "1"
            assert element.find("c:numFmt", chart_ns).get("formatCode") == "0.0%"

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


def _cached_cell(sheet_xml, address):
    from xml.etree import ElementTree as ET
    root = ET.fromstring(sheet_xml)
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    cell = root.find(f".//x:c[@r='{address}']", ns)
    assert cell is not None, f"No existe {address}"
    value = cell.find("x:v", ns)
    formula = cell.find("x:f", ns)
    # XlsxWriter guarda resultados "" como <v/> (Element.text = None).
    return ((value.text or "") if value is not None else None,
            formula.text if formula is not None else None)


def test_monthly_cards_use_last_cutoff_of_each_month_and_month_to_month_delta():
    # Agosto 15%, septiembre 30% y octubre 20% lead->visita.
    # El cambio de la última SEMANA de octubre sería -25 pp (45% -> 20%);
    # la tarjeta debe mostrar el cambio MENSUAL septiembre -> octubre = -10 pp.
    examples = [
        _snapshot("2026-08-31", (100, 10, 5), (100, 20, 5)),
        _snapshot("2026-09-21", (100, 30, 5), (100, 30, 5)),
        _snapshot("2026-10-12", (100, 50, 5), (100, 40, 5)),
        _snapshot("2026-10-19", (100, 15, 8), (100, 25, 8)),
    ]
    workbook = create_workbook(
        examples[-1], examples, OPTIONS, is_global=True
    )
    with ZipFile(BytesIO(workbook)) as archive:
        summary = archive.read("xl/worksheets/sheet1.xml")
        trend = archive.read("xl/worksheets/sheet3.xml")
        for cell, month in (("T2", "2026-08"),
                            ("U2", "2026-09"), ("V2", "2026-10")):
            cached, formula = _cached_cell(trend, cell)
            assert cached == month
            assert "LOOKUP" in formula
            assert "$S$3" in formula
        for cell, expected in (
            ("A11", 0.15), ("D11", 0.30), ("G11", 0.20),
            ("H11", 10 / 30), ("K11", 10 / 60), ("N11", 16 / 40),
            ("O11", 10 / 200), ("R11", 10 / 200), ("U11", 16 / 200),
        ):
            cached, formula = _cached_cell(summary, cell)
            assert float(cached) == pytest.approx(expected)
            assert "LOOKUP" in formula
        for cell, expected in (
            ("A12", -10), ("H12", (16/40 - 10/60) * 100),
            ("O12", (16/200 - 10/200) * 100),
        ):
            cached, formula = _cached_cell(summary, cell)
            assert float(cached) == pytest.approx(expected)
            assert "11" in formula
        for cell, month in (("A10", "Ago 2026"),
                            ("D10", "Sep 2026"), ("G10", "Oct 2026")):
            cached, formula = _cached_cell(summary, cell)
            assert cached == month
            assert "CHOOSE" in formula
        caption, formula = _cached_cell(summary, "A13")
        assert "Sep → Oct" in caption
        assert "Sin comparación mensual" in formula
        assert "Tendencia - datos" in _cached_cell(summary, "A11")[1]
        assert "Tendencia - datos" in _cached_cell(summary, "G11")[1]


def test_monthly_cards_with_only_one_month_do_not_invent_comparisons():
    data = create_workbook(
        _snapshot("2026-10-19"), [_snapshot("2026-10-19")],
        OPTIONS, is_global=True,
    )
    with ZipFile(BytesIO(data)) as archive:
        summary = archive.read("xl/worksheets/sheet1.xml")
        trend = archive.read("xl/worksheets/sheet3.xml")
        assert _cached_cell(trend, "T2")[0] == ""
        assert _cached_cell(trend, "U2")[0] == ""
        assert _cached_cell(trend, "V2")[0] == "2026-10"
        assert _cached_cell(summary, "A11")[0] == ""
        assert _cached_cell(summary, "D11")[0] == ""
        assert float(_cached_cell(summary, "G11")[0]) == pytest.approx(0.2)
        assert _cached_cell(summary, "A12")[0] == ""
        assert _cached_cell(summary, "A13")[0] == "Sin comparación mensual"


def test_resumen_visual_uses_real_month_dates_and_compact_scope_dropdown():
    from xml.etree import ElementTree as ET

    workbook = create_workbook(
        _snapshot("2026-10-19"),
        [
            _snapshot("2026-08-31"), _snapshot("2026-09-21"),
            _snapshot("2026-10-19"),
        ],
        OPTIONS, is_global=True,
    )
    with ZipFile(BytesIO(workbook)) as archive:
        ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        summary = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        calc = ET.fromstring(archive.read("xl/worksheets/sheet3.xml"))
        styles = ET.fromstring(archive.read("xl/styles.xml"))
        shared = archive.read("xl/sharedStrings.xml").decode()
        book_xml = archive.read("xl/workbook.xml").decode()

        def cell(root, reference):
            entry = root.find(f".//x:sheetData/x:row/x:c[@r='{reference}']", ns)
            assert entry is not None, reference
            return entry

        def cell_cached(root, reference):
            entry = cell(root, reference)
            data = entry.find("x:v", ns)
            assert data is not None, reference
            return data.text

        first = str((date(2026, 8, 1) - date(1899, 12, 30)).days)
        latest = str((date(2026, 10, 1) - date(1899, 12, 30)).days)
        assert cell_cached(summary, "F4") == first
        assert cell_cached(summary, "K4") == latest
        assert cell(summary, "F4").attrib.get("t", "n") == "n"
        assert cell(summary, "K4").attrib.get("t", "n") == "n"
        num_formats = [
            el.get("formatCode", "")
            for el in styles.findall(".//x:numFmts/x:numFmt", ns)
        ]
        assert any("mmmm-yy" in val and "es-MX" in val for val in num_formats)
        assert "FunnelMeses" in book_xml

        # S3 y S4 conservan claves YYYY-MM para comparaciones y filtros;
        # leen la FECHA de los desplegables, nunca el texto mostrado.
        for address, date_ref in (("S3", "Resumen!$F$4"),
                                  ("S4", "Resumen!$K$4")):
            formula = cell(calc, address).find("x:f", ns).text
            assert "YEAR(" + date_ref + ")" in formula
            assert "MONTH(" + date_ref + ")" in formula

        merged = {
            item.attrib["ref"]
            for item in summary.findall(".//x:mergeCells/x:mergeCell", ns)
        }
        assert "K5:O5" in merged
        assert "K6:O6" in merged
        assert "K6:U6" not in merged
        assert "REGIÓN / SUCURSAL" in shared
        assert "Cortes acumulados mensuales (MTD)" not in shared
        assert cell(summary, "A7").find("x:v", ns) is None if summary.find(
            ".//x:c[@r='A7']", ns
        ) is not None else True


def test_resumen_visual_three_cards_have_distinct_fills_and_medium_outline():
    from xml.etree import ElementTree as ET

    workbook = create_workbook(
        _snapshot("2026-10-19"),
        [
            _snapshot("2026-08-31"), _snapshot("2026-09-21"),
            _snapshot("2026-10-19"),
        ],
        OPTIONS, is_global=True,
    )
    with ZipFile(BytesIO(workbook)) as archive:
        ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        summary = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        styles = ET.fromstring(archive.read("xl/styles.xml"))
        formats = styles.find("x:cellXfs", ns)
        borders = styles.find("x:borders", ns)
        fills = styles.find("x:fills", ns)

        def style_of(cell):
            entry = summary.find(f".//x:c[@r='{cell}']", ns)
            assert entry is not None, cell
            return formats[int(entry.attrib["s"])]

        fill_ids = {style_of(x).get("fillId") for x in ("A11", "H11", "O11")}
        assert len(fill_ids) == 3
        for idx in fill_ids:
            entry = fills[int(idx)]
            assert entry.find(".//x:fgColor", ns) is not None

        for cell in ("A10", "H10", "O10"):
            border = borders[int(style_of(cell).get("borderId"))]
            assert border.find("x:top", ns).get("style") == "medium"
            assert border.find("x:left", ns).get("style") == "medium"
        for cell in ("G11", "N11", "U11"):
            border = borders[int(style_of(cell).get("borderId"))]
            assert border.find("x:bottom", ns).get("style") == "medium"
            assert border.find("x:right", ns).get("style") == "medium"


def test_linked_period_filters_show_effective_dates_and_custom_inputs():
    """Presets control effective dates; customized months are separate inputs."""
    from xml.etree import ElementTree as ET

    workbook = create_workbook(
        _snapshot("2026-10-19"),
        [
            _snapshot("2026-08-31"), _snapshot("2026-09-21"),
            _snapshot("2026-10-19"),
        ],
        OPTIONS, is_global=True,
    )
    with ZipFile(BytesIO(workbook)) as archive:
        ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        panel = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        trend = ET.fromstring(archive.read("xl/worksheets/sheet3.xml"))

        start_serial = str((date(2026, 8, 1) - date(1899, 12, 30)).days)
        end_serial = str((date(2026, 10, 1) - date(1899, 12, 30)).days)
        for target, cached in (("F4", start_serial), ("K4", end_serial),
                               ("P4", start_serial), ("S4", end_serial)):
            value, formula = _cached_cell(archive.read(
                "xl/worksheets/sheet1.xml"), target)
            assert value == cached

        start_formula = _cached_cell(
            archive.read("xl/worksheets/sheet1.xml"), "F4"
        )[1]
        end_formula = _cached_cell(
            archive.read("xl/worksheets/sheet1.xml"), "K4"
        )[1]
        assert start_formula.startswith('IF($A$4="Personalizado",$P$4,')
        assert 'Todo el histórico' in start_formula
        assert 'MIN(' in start_formula
        assert 'EDATE(' in start_formula
        assert 'Últimos 3 meses' in start_formula
        assert 'Últimos 6 meses' in start_formula
        assert end_formula.startswith('IF($A$4="Personalizado",$S$4,')
        assert "DATE(" in end_formula

        # F4/K4 son visualizaciones calculadas y ya NO tienen desplegable
        # manual. P4/S4 son los únicos campos editables del rango.
        validations = {
            item.attrib["sqref"]: item
            for item in panel.findall(".//x:dataValidations/x:dataValidation", ns)
        }
        for field in ("F4", "K4"):
            assert field in validations
            assert validations[field].get("type") == "custom"
            assert validations[field].get("errorStyle") == "stop"
            assert validations[field].find("x:formula1", ns).text == "FALSE"
        for field in ("P4", "S4"):
            assert field in validations
            assert validations[field].find("x:formula1", ns).text == "FunnelMeses"
        assert "A4" in validations

        # Las fórmulas de filtrado ya no contienen un IF separado por
        # Periodo: usan exclusivamente las dos fechas efectivas.
        for address, selector in (("S3", "Resumen!$F$4"),
                                  ("S4", "Resumen!$K$4")):
            cell = trend.find(f".//x:c[@r='{address}']/x:f", ns)
            assert cell is not None
            assert "YEAR(" + selector + ")" in cell.text
            assert "MONTH(" + selector + ")" in cell.text
            assert "Personalizado" not in cell.text
        assert _cached_cell(archive.read("xl/worksheets/sheet3.xml"), "S3")[0] == "2026-08"
        assert _cached_cell(archive.read("xl/worksheets/sheet3.xml"), "S4")[0] == "2026-10"

        # Entradas de personalizado se resaltan únicamente al seleccionarlo.
        conditions = {
            item.attrib["sqref"]: item
            for item in panel.findall(".//x:conditionalFormatting", ns)
        }
        for span in ("P4:R4", "S4:U4", "P3:R3", "S3:U3"):
            assert span in conditions
        assert "Desde debe ser anterior o igual a Hasta" in (
            _cached_cell(archive.read("xl/worksheets/sheet1.xml"), "P5")[1]
        )


def test_month_start_preset_crosses_year_without_locale_mask():
    # En enero, "Últimos 3 meses" empieza en noviembre anterior.
    workbook = create_workbook(
        _snapshot("2027-01-18"),
        [_snapshot("2026-11-30"), _snapshot("2026-12-28"),
         _snapshot("2027-01-18")],
        OPTIONS, is_global=True,
    )
    with ZipFile(BytesIO(workbook)) as archive:
        panel = archive.read("xl/worksheets/sheet1.xml")
        calc = archive.read("xl/worksheets/sheet3.xml")
        expected = str((date(2026, 11, 1) - date(1899, 12, 30)).days)
        assert _cached_cell(panel, "F4")[0] == expected
        assert _cached_cell(calc, "S3")[0] == "2026-11"
        assert _cached_cell(calc, "S4")[0] == "2027-01"
        assert "EDATE" in _cached_cell(panel, "F4")[1]
        assert '"yyyy-mm"' not in _cached_cell(panel, "F4")[1]
