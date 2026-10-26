"""Generación del Excel histórico del Funnel Original, sin macros ni cambios DB."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

import xlsxwriter
from xlsxwriter.utility import xl_col_to_name

FIRST_MONTH = date(2026, 7, 1)
METRICS = (
    ("Leads", "leads_meta"), ("Visitantes totales", "visits_total"),
    ("Ventas digitales", "sales_digital"),
    ("Ventas digitales orgánicas", "sales_digital_organic"),
    ("Venta web", "sales_web"), ("Venta BTL", "sales_btl"),
    ("Ventas totales", "sales_total"), ("Inversión", "investment"),
    ("Ingreso digital", "revenue_digital"), ("Ingreso web", "revenue_web"),
    ("Ingreso BTL", "revenue_btl"), ("Ingreso total", "revenue_total"),
)
INDICATORS = ("Lead → visita", "Visita → venta digital", "Lead → venta")
PERIODS = ("Últimos 3 meses", "Últimos 6 meses", "Últimos 12 meses",
           "Todo el histórico", "Personalizado")
COLORS = ("#4472C4", "#C0504D", "#84A93A")


def closed_business_date(today: date | None = None) -> date:
    return (today or datetime.now(ZoneInfo("America/Tijuana")).date()) - timedelta(days=1)


def find_weekly_cutoffs(
    last_cutoff: date,
    available: Callable[[date], Sequence[date]],
    *,
    today: date | None = None,
    first_month: date = FIRST_MONTH,
) -> list[date]:
    """Solo lunes completos de la intersección canónica, disponibles desde martes."""
    end = min(last_cutoff, closed_business_date(today))
    if first_month > end:
        return []
    year, month = first_month.year, first_month.month
    found: set[date] = set()
    while (year, month) <= (end.year, end.month):
        for cut in available(date(year, month, 1)):
            if cut.weekday() == 0 and first_month <= cut <= end:
                found.add(cut)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return sorted(found)


def number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def scopes_from_access(
    scope_options: Sequence[Mapping[str, Any]], is_global: bool
) -> tuple[list[tuple[str, str]], dict[int, tuple[str, str]]]:
    entries = [("Todo Ultra" if is_global else "Todas las autorizadas", "ALL")]
    branches: dict[int, tuple[str, str]] = {}
    regions: dict[str, str] = {}
    for branch in scope_options:
        bid = int(branch["sucursal_id"])
        region_key = ("R:" + str(branch["region_id"])
                      if branch.get("region_id") is not None else "R:SIN_REGION")
        region_name = str(branch.get("region") or "Sin región")
        branches[bid] = (region_key, "S:" + str(bid))
        regions[region_key] = region_name
    entries += [("Región | " + name, key)
                for key, name in sorted(regions.items(), key=lambda p: p[1])]
    entries += [("Sucursal | " + str(branch["sucursal"]), "S:" + str(branch["sucursal_id"]))
                for branch in sorted(scope_options, key=lambda b: str(b["sucursal"]).lower())]
    return entries, branches


def create_workbook(
    daily: Mapping[str, Any],
    weekly: Sequence[Mapping[str, Any]],
    scope_options: Sequence[Mapping[str, Any]],
    *,
    is_global: bool,
) -> bytes:
    """La selección por ids y las tasas sobre totales se calculan en Excel."""
    latest_date = date.fromisoformat(str(daily["selected_cutoff_date"]))
    weekly = sorted(weekly, key=lambda p: p["selected_cutoff_date"])
    months = sorted({str(p["selected_cutoff_date"])[:7] for p in weekly})
    first_month = months[0] if months else latest_date.strftime("%Y-%m")
    last_month = months[-1] if months else latest_date.strftime("%Y-%m")
    scope_labels, authorized = scopes_from_access(scope_options, is_global)
    # Catálogos después de las series (3 por mes); nunca pisar datos al crecer.
    catalog_col = max(30, 14 + 3 * len(months))
    catalog_name = xl_col_to_name(catalog_col)
    catalog_key = xl_col_to_name(catalog_col + 1)
    catalog_month = xl_col_to_name(catalog_col + 2)
    all_rows = []
    for snapshot in weekly:
        day = date.fromisoformat(str(snapshot["selected_cutoff_date"]))
        for branch in snapshot.get("branches", []):
            bid = int(branch["sucursal_id"])
            if bid not in authorized:
                continue
            reg, key = authorized[bid]
            all_rows.append((day, day.strftime("%Y-%m"), reg, key,
                             number(branch.get("leads_meta")),
                             number(branch.get("visits_total")),
                             number(branch.get("sales_digital"))))

    stream = BytesIO()
    book = xlsxwriter.Workbook(stream, {"in_memory": True})
    book.set_calc_mode("auto")
    book.set_properties({"title": "Funnel Original - Tendencia semanal",
                         "author": "Suite Ultra"})
    navy = book.add_format({"bg_color": "#1C2E55", "font_color": "white",
                            "bold": True, "valign": "vcenter"})
    purple = book.add_format({"bg_color": "#332D86", "font_color": "white",
                              "bold": True, "align": "center"})
    soft = book.add_format({"bg_color": "#EDF2FE", "font_color": "#172C58",
                            "align": "center", "valign": "vcenter"})
    choice = book.add_format({"bg_color": "#D8F8E9", "font_color": "#145C4A",
                              "bold": True, "align": "center"})
    big_pct = book.add_format({"num_format": "0.0%", "font_size": 19,
                               "bold": True, "align": "center",
                               "bg_color": "#EDF2FE", "font_color": "#172C58"})
    pp = book.add_format({"num_format": '+0.0" pp";-0.0" pp";0.0" pp"',
                          "align": "center", "font_color": "#70819B"})
    small = book.add_format({"font_size": 9, "font_color": "#445575"})
    integer = book.add_format({"num_format": "#,##0"})
    currency = book.add_format({"num_format": '$#,##0.00'})
    percent = book.add_format({"num_format": "0.0%"})
    day_fmt = book.add_format({"num_format": "dd mmm yyyy"})
    header = book.add_format({"bg_color": "#38445E", "font_color": "white",
                              "bold": True, "align": "center", "text_wrap": True})

    panel = book.add_worksheet("Resumen")
    panel.set_tab_color("#332D86")
    panel.hide_gridlines(2)
    panel.set_column("A:U", 6.4)
    panel.set_row(0, 29)
    panel.merge_range("A1:U1", "TENDENCIAS DEL FUNNEL  |  Histórico de lunes", navy)
    for merged, title in (("A3:E3", "PERIODO"), ("F3:J3", "DESDE"),
                          ("K3:O3", "HASTA"), ("A5:E5", "INDICADOR"),
                          ("K5:O5", "ÁMBITO")):
        panel.merge_range(merged, title, navy)
    for area, value in (("A4:E4", PERIODS[0]), ("F4:J4", first_month),
                        ("K4:O4", last_month), ("A6:E6", INDICATORS[0]),
                        ("K6:U6", scope_labels[0][0])):
        panel.merge_range(area, value, choice)
    panel.data_validation("A4", {"validate": "list", "source": list(PERIODS)})
    panel.data_validation("A6", {"validate": "list",
                                 "source": list(INDICATORS) + ["Comparar las tres"]})
    # Excel exige nombres definidos para listas ubicadas en otra hoja.
    book.define_name(
        "FunnelAmbitos",
        "='Tendencia - datos'!$" + catalog_name + "$2:$"
        + catalog_name + "$" + str(len(scope_labels) + 1),
    )
    book.define_name(
        "FunnelMeses",
        "='Tendencia - datos'!$" + catalog_month + "$2:$"
        + catalog_month + "$" + str(max(2, len(months) + 1)),
    )
    panel.data_validation("K6", {"validate": "list", "source": "=FunnelAmbitos"})
    panel.data_validation("F4", {"validate": "list", "source": "=FunnelMeses"})
    panel.data_validation("K4", {"validate": "list", "source": "=FunnelMeses"})
    panel.merge_range("A7:U7", "Cortes acumulados mensuales (MTD) · Solo lunes completos · Sin unir meses", small)
    panel.merge_range("A8:U8", "", small)
    for area, text in (("A9:G9", "LEAD → VISITA"),
                       ("H9:N9", "VISITA → VENTA DIGITAL"), ("O9:U9", "LEAD → VENTA")):
        panel.merge_range(area, text, purple)
    for prefix, last in (("A", "G"), ("H", "N"), ("O", "U")):
        panel.merge_range(f"{prefix}10:{last}11", "", big_pct)
        panel.merge_range(f"{prefix}12:{last}12", "", pp)

    data = book.add_worksheet("Base semanal")
    data.hide_gridlines(2)
    data.freeze_panes(1, 4)
    data.set_column("A:A", 16)
    data.set_column("B:D", 17)
    data.set_column("E:G", 18)
    for col, title in enumerate(("Corte", "Mes", "Region key", "Sucursal key",
                                  "Leads", "Visitas", "Ventas digitales")):
        data.write(0, col, title, header)
    for r, (day, month, region, branch, leads, visits, digital) in enumerate(all_rows, 1):
        data.write_datetime(r, 0, datetime.combine(day, datetime.min.time()), day_fmt)
        for col, text in ((1, month), (2, region), (3, branch)):
            data.write_string(r, col, text)
        for col, value in ((4, leads), (5, visits), (6, digital)):
            if value is not None:
                data.write_number(r, col, value, integer)

    calc = book.add_worksheet("Tendencia - datos")
    calc.freeze_panes(10, 2)
    calc.set_column("A:A", 17)
    calc.set_column("B:B", 13)
    calc.set_column("C:Z", 17)
    calc.set_column(
        catalog_name + ":" + catalog_month, 30, None, {"hidden": True}
    )
    for i, (text, key) in enumerate(scope_labels, 1):
        calc.write_string(i, catalog_col, text)
        calc.write_string(i, catalog_col + 1, key)
    for i, month in enumerate(months or [last_month], 1):
        calc.write_string(i, catalog_col + 2, month)
    calc.write("L1", "Ámbito seleccionado", navy)
    calc.write_formula(
        "M2",
        '=IFERROR(VLOOKUP(Resumen!$K$6,
    calc.write("R1", "Último mes", navy)
    calc.write_string("R2", last_month)
    calc.write("R3", "Desde efectivo", navy)
    calc.write_formula(
        "S3",
        '=IF(Resumen!$A$4="Personalizado",Resumen!$F$4,'
        'IF(Resumen!$A$4="Todo el histórico","0000-00",'
        'TEXT(EDATE(DATE(VALUE(LEFT($R$2,4)),VALUE(RIGHT($R$2,2)),1),'
        '-IF(Resumen!$A$4="Últimos 3 meses",2,'
        'IF(Resumen!$A$4="Últimos 6 meses",5,11))),"yyyy-mm")))',
    )
    calc.write("R4", "Hasta efectivo", navy)
    calc.write_formula("S4", '=IF(Resumen!$A$4="Personalizado",Resumen!$K$4,$R$2)')
    for c, title in enumerate(("Corte", "Mes", "Leads", "Visitas", "Venta digital",
                               *INDICATORS, "Incluido", "Δ L/V", "Δ V/V",
                               "Δ L/Venta")):
        calc.write(9, c, title, header)

    series = [(month, metric, 12 + idx)
              for idx, (month, metric) in
              enumerate((month, metric) for month in months for metric in range(3))]
    for month, metric, col in series:
        calc.write(9, col, INDICATORS[metric] + " " + month, header)

    final_base_row = max(2, len(all_rows) + 1)
    def count_formula(col: str, excel_row: int) -> str:
        rng = f"'Base semanal'!{col}2:{col}{final_base_row}"
        dates = f"'Base semanal'!A2:A{final_base_row}"
        regions = f"'Base semanal'!C2:C{final_base_row}"
        branches = f"'Base semanal'!D2:D{final_base_row}"
        return (
            f'=IF($M$2="ALL",SUMIF({dates},$A{excel_row},{rng}),'
            f'IF(LEFT($M$2,2)="R:",SUMIFS({rng},{dates},$A{excel_row},'
            f'{regions},$M$2),SUMIFS({rng},{dates},$A{excel_row},'
            f'{branches},$M$2)))'
        )

    for idx, snapshot in enumerate(weekly, start=10):
        r = idx + 1
        day = date.fromisoformat(str(snapshot["selected_cutoff_date"]))
        calc.write_datetime(idx, 0, datetime.combine(day, datetime.min.time()), day_fmt)
        calc.write_string(idx, 1, day.strftime("%Y-%m"))
        for col, base_col in ((2, "E"), (3, "F"), (4, "G")):
            calc.write_formula(idx, col, count_formula(base_col, r), integer)
        for col, numerator, denominator in ((5, "D", "C"), (6, "E", "D"),
                                            (7, "E", "C")):
            calc.write_formula(idx, col,
                               f'=IFERROR(IF({denominator}{r}=0,NA(),'
                               f'{numerator}{r}/{denominator}{r}),NA())',
                               percent)
        calc.write_formula(idx, 8, f'=IF(AND(B{r}>=$S$3,B{r}<=$S$4),1,"")')
        for col, pct_col in ((9, "F"), (10, "G"), (11, "H")):
            calc.write_formula(idx, col, (f'=IF(B{r}=B{r-1},'
                                          f'{pct_col}{r}-{pct_col}{r-1},NA())'
                                          if idx > 10 else "=NA()"), pp)
        for month, metric, col in series:
            metric_col = ("F", "G", "H")[metric]
            calc.write_formula(
                idx, col,
                f'=IF(AND($B{r}="{month}",$I{r}=1,'
                f'OR(Resumen!$A$6="Comparar las tres",'
                f'Resumen!$A$6="{INDICATORS[metric]}")),'
                f'IFERROR({metric_col}{r},NA()),NA())',
                percent,
            )

    last = max(11, len(weekly) + 10)
    for col, data_col, diff_col in (("A", "F", "J"), ("H", "G", "K"),
                                    ("O", "H", "L")):
        source = f"'Tendencia - datos'!{data_col}11:{data_col}{last}"
        diffs = f"'Tendencia - datos'!{diff_col}11:{diff_col}{last}"
        condition = f"'Tendencia - datos'!I11:I{last}=1"
        panel.write_formula(
            col + "10", f'=IFERROR(LOOKUP(2,1/({condition}),{source}),"")', big_pct
        )
        panel.write_formula(
            col + "12", f'=IFERROR(LOOKUP(2,1/({condition}),{diffs})*100,"")', pp
        )
    # La descripción sigue el último lunes del periodo seleccionado.
    condition = f"'Tendencia - datos'!I11:I{last}=1"
    date_source = f"'Tendencia - datos'!A11:A{last}"
    panel.write_formula(
        "A8",
        '=IFERROR("Corte actual: "&TEXT(LOOKUP(2,1/(' + condition + '),'
        + date_source + '),"dd mmm yyyy")&"  ·  Ámbito: "&$K$6'
        + '&"  ·  "&COUNTIF(\'Tendencia - datos\'!I11:I'
        + str(last) + ',1)&" cortes disponibles",'
        + '"Sin lunes completos en el periodo seleccionado")',
        small,
    )
    if weekly:
        chart = book.add_chart({"type": "line"})
        for month, metric, col in series:
            chart.add_series({
                "name": INDICATORS[metric] + " · " + month,
                "categories": ["Tendencia - datos", 10, 0, last - 1, 0],
                "values": ["Tendencia - datos", 10, col, last - 1, col],
                "line": {"color": COLORS[metric], "width": 2.5},
                "marker": {"type": "circle", "size": 3},
            })
        chart.set_title({"name": "Evolución de conversiones (%)"})
        chart.set_y_axis({"num_format": "0%", "min": 0,
                          "major_gridlines": {"visible": True}})
        chart.set_x_axis({"date_axis": True, "num_format": "dd mmm"})
        chart.set_legend({"none": True})
        chart.show_blanks_as("gap")
        chart.set_size({"width": 1190, "height": 490})
        panel.insert_chart("A14", chart)
        for cell, metric, color in (("B40", INDICATORS[0], COLORS[0]),
                                    ("I40", INDICATORS[1], COLORS[1]),
                                    ("P40", INDICATORS[2], COLORS[2])):
            fmt = book.add_format({"font_color": color, "bold": True})
            panel.write_string(cell, "● " + metric, fmt)
    else:
        panel.merge_range("A15:U17", "Sin lunes completos disponibles.", soft)

    def make_detail(name: str, snapshot: Mapping[str, Any]) -> None:
        ws = book.add_worksheet(name[:31])
        ws.hide_gridlines(2)
        ws.freeze_panes(4, 1)
        ws.set_column("A:A", 29)
        ws.set_column("B:K", 16)
        ws.set_column("L:S", 19)
        ws.merge_range("A1:S1", "FUNNEL VENTA NUEVA · ORIGINAL", navy)
        ws.merge_range("A2:S2", "Corte " + str(snapshot["selected_cutoff_date"])
                       + " · visitas registradas", soft)
        headings = (
            "Sucursal", *(x[0] for x in METRICS[:7]),
            *INDICATORS, *(x[0] for x in METRICS[7:]), "CPL", "CPT", "CAC"
        )
        for c, title in enumerate(headings):
            ws.write(3, c, title, header)
        region_names = {int(x["sucursal_id"]): str(x.get("region") or "Sin región")
                        for x in scope_options}
        groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for b in snapshot.get("branches", []):
            bid = int(b["sucursal_id"])
            if bid in authorized:
                groups[region_names.get(bid, "Sin región")].append(b)
        row, subtotals = 4, []
        for region, branches in sorted(groups.items()):
            ws.merge_range(row, 0, row, 18, "REGIÓN " + region.upper(), soft)
            row += 1
            first = row
            for b in sorted(branches, key=lambda item: str(item["sucursal"])):
                ws.write_string(row, 0, str(b["sucursal"]))
                for c, (_, key) in enumerate(METRICS[:7], start=1):
                    v = number(b.get(key))
                    if v is not None:
                        ws.write_number(row, c, v, integer)
                for c, f in ((8, f'=IFERROR(C{row+1}/B{row+1},"")'),
                             (9, f'=IFERROR(D{row+1}/C{row+1},"")'),
                             (10, f'=IFERROR(D{row+1}/B{row+1},"")')):
                    ws.write_formula(row, c, f, percent)
                for c, (_, key) in enumerate(METRICS[7:], start=11):
                    v = number(b.get(key))
                    if v is not None:
                        ws.write_number(row, c, v, currency)
                for c, formula in (
                    (16, f'=IFERROR(L{row+1}/B{row+1},"")'),
                    (17, f'=IFERROR(L{row+1}/C{row+1},"")'),
                    (18, f'=IFERROR(L{row+1}/(D{row+1}+E{row+1}),"")'),
                ):
                    ws.write_formula(row, c, formula, currency)
                row += 1
            subtotal = row + 1
            ws.write(row, 0, "SUBTOTAL REGIÓN", navy)
            for c in list(range(1, 8)) + list(range(11, 16)):
                x = xl_col_to_name(c)
                ws.write_formula(row, c, f"=SUM({x}{first+1}:{x}{row})",
                                 currency if c >= 11 else integer)
            for c, num, den in ((8, "C", "B"), (9, "D", "C"), (10, "D", "B")):
                ws.write_formula(row, c, f'=IFERROR({num}{subtotal}/{den}{subtotal},"")', percent)
            subtotals.append(subtotal)
            row += 2
        ws.write(row, 0, "TOTAL", navy)
        for c in list(range(1, 8)) + list(range(11, 16)):
            x = xl_col_to_name(c)
            formula = "=" + "+".join(f"{x}{r}" for r in subtotals) if subtotals else "=0"
            ws.write_formula(row, c, formula, currency if c >= 11 else integer)
        for c, num, den in ((8, "C", "B"), (9, "D", "C"), (10, "D", "B")):
            ws.write_formula(row, c, f'=IFERROR({num}{row+1}/{den}{row+1},"")', percent)
        ws.autofilter(3, 0, 3, 18)

    make_detail("Detalle diario", daily)
    for snapshot in weekly:
        make_detail("Lun " + str(snapshot["selected_cutoff_date"]), snapshot)
    book.close()
    return stream.getvalue()
