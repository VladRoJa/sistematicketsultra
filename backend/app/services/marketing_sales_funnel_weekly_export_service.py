"""Generación del Excel histórico del Funnel Original, sin macros ni cambios DB."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

import xlsxwriter
from xlsxwriter.utility import xl_col_to_name

from app.services.marketing_sales_funnel_original_sheet_service import (
    write_original_operational_sheet,
)

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
    initial_counters = []
    for snapshot in weekly:
        authorized_branches = [
            branch for branch in snapshot.get("branches", [])
            if int(branch["sucursal_id"]) in authorized
        ]
        initial_counters.append(tuple(
            sum(number(b.get(metric)) or 0 for b in authorized_branches)
            for metric in ("leads_meta", "visits_total", "sales_digital")
        ))
    initial_rates = [
        (visits / leads if leads else None,
         digital / visits if visits else None,
         digital / leads if leads else None)
        for leads, visits, digital in initial_counters
    ]
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
    monthly_pct = book.add_format({"num_format": "0.0%", "font_size": 13,
                                   "bold": True, "align": "center",
                                   "bg_color": "#EDF2FE",
                                   "font_color": "#172C58"})
    monthly_label = book.add_format({"font_size": 9, "align": "center",
                                     "bg_color": "#EDF2FE",
                                     "font_color": "#566C95"})
    monthly_arrow = book.add_format({"font_size": 15, "bold": True,
                                     "align": "center",
                                     "bg_color": "#EDF2FE",
                                     "font_color": "#344C78"})
    monthly_caption = book.add_format({"font_size": 8, "align": "center",
                                       "font_color": "#627492"})
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
    # Tres cortes mensuales por indicador: etiquetas en fila 10,
    # tasas en 11, variación intermensual en 12 y comparación en 13.
    panel.set_row(9, 18)
    panel.set_row(10, 25)
    panel.set_row(11, 18)
    panel.set_row(12, 17)
    for first, middle, latest, arrows, span in (
        ("A", "D", "G", ("C", "F"), ("A", "G")),
        ("H", "K", "N", ("J", "M"), ("H", "N")),
        ("O", "R", "U", ("Q", "T"), ("O", "U")),
    ):
        for left, right in ((first, xl_col_to_name(ord(first) - 64)),
                            (middle, xl_col_to_name(ord(middle) - 64))):
            panel.merge_range(f"{left}10:{right}10", "", monthly_label)
            panel.merge_range(f"{left}11:{right}11", "", monthly_pct)
        panel.write_blank(f"{latest}10", None, monthly_label)
        panel.write_blank(f"{latest}11", None, monthly_pct)
        for arrow in arrows:
            panel.write_blank(f"{arrow}11", None, monthly_arrow)
        panel.merge_range(f"{span[0]}12:{span[1]}12", "", pp)
        panel.merge_range(f"{span[0]}13:{span[1]}13", "", monthly_caption)

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
        '=IFERROR(VLOOKUP(Resumen!$K$6,$' + catalog_name
        + '$2:$' + catalog_key + '$' + str(len(scope_labels) + 1)
        + ',2,FALSE),"ALL")',
        None, "ALL",
    )
    calc.write("R1", "Último mes", navy)
    calc.write_string("R2", last_month)
    calc.write("R3", "Desde efectivo", navy)
    # No usar TEXT(..., "yyyy-mm"): yyyy es literal en algunas
    # configuraciones de Excel en español. Año/mes numéricos son invariantes.
    month_shift = (
        'IF(Resumen!$A$4="Últimos 3 meses",2,'
        'IF(Resumen!$A$4="Últimos 6 meses",5,11))'
    )
    first_date = (
        'EDATE(DATE(VALUE(LEFT($R$2,4)),VALUE(RIGHT($R$2,2)),1),-'
        + month_shift + ')'
    )
    first_month_formula = (
        '=IF(Resumen!$A$4="Personalizado",Resumen!$F$4,'
        'IF(Resumen!$A$4="Todo el histórico","0000-00",'
        'YEAR(' + first_date + ')&"-"&'
        'RIGHT("0"&MONTH(' + first_date + '),2)))'
    )
    calc.write_formula(
        "S3", first_month_formula,
        None, (f"{int(last_month[:4]) - (int(last_month[5:]) <= 2)}-"
               f"{((int(last_month[5:]) - 3) % 12) + 1:02d}"),
    )
    calc.write("R4", "Hasta efectivo", navy)
    calc.write_formula("S4", '=IF(Resumen!$A$4="Personalizado",Resumen!$K$4,$R$2)',
                       None, last_month)
    # Tres últimos meses CON CORTES disponibles dentro del periodo elegido.
    # T2/U2/V2 responden al selector; admiten periodos con menos de 3 meses.
    year, month = int(last_month[:4]), int(last_month[5:])
    start_month_index = year * 12 + month - 1 - 2
    default_start = f"{start_month_index // 12:04d}-{start_month_index % 12 + 1:02d}"
    visible_months = [ym for ym in months if default_start <= ym <= last_month]
    initial_month_keys = ([""] * 3 + visible_months[-3:])[-3:]
    month_col_range = (
        f"${catalog_month}$2:${catalog_month}${max(2, len(months) + 1)}"
    )
    calc.write("T1", "Mes anterior 2", small)
    calc.write("U1", "Mes anterior", small)
    calc.write("V1", "Último mes", small)
    for target, prior, cache in (
        ("V2", "$S$4", initial_month_keys[2]),
        ("U2", "$V$2", initial_month_keys[1]),
        ("T2", "$U$2", initial_month_keys[0]),
    ):
        condition = (
            f"({month_col_range}<={prior})" if target == "V2"
            else f"({month_col_range}<{prior})"
        )
        month_formula = (
            '=IFERROR(LOOKUP(2,1/(('
            + month_col_range + '>=$S$3)*' + condition
            + '),' + month_col_range + '),"")'
        ) if weekly else '=""'
        calc.write_formula(target, month_formula, None, cache)

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

    # Valores almacenados para visualizar la gráfica antes del primer recálculo.
    # Las fórmulas permanecen y responden a filtros al cambiar las selecciones.
    for idx, snapshot in enumerate(weekly, start=10):
        si = idx - 10
        r = idx + 1
        day = date.fromisoformat(str(snapshot["selected_cutoff_date"]))
        month = day.strftime("%Y-%m")
        calc.write_datetime(idx, 0, datetime.combine(day, datetime.min.time()), day_fmt)
        calc.write_string(idx, 1, month)
        for col, base_col, cache in (
            (2, "E", initial_counters[si][0]),
            (3, "F", initial_counters[si][1]),
            (4, "G", initial_counters[si][2]),
        ):
            calc.write_formula(idx, col, count_formula(base_col, r), integer, cache)
        for metric, col, numerator, denominator in (
            (0, 5, "D", "C"),
            (1, 6, "E", "D"),
            (2, 7, "E", "C"),
        ):
            cached = initial_rates[si][metric]
            calc.write_formula(
                idx, col,
                f'=IFERROR(IF({denominator}{r}=0,NA(),'
                f'{numerator}{r}/{denominator}{r}),NA())',
                percent, cached if cached is not None else "#N/A",
            )
        calc.write_formula(idx, 8, f'=IF(AND(B{r}>=$S$3,B{r}<=$S$4),1,"")',
                           None, 1)
        for metric, col, pct_col in ((0, 9, "F"), (1, 10, "G"), (2, 11, "H")):
            previous = initial_rates[si - 1][metric] if si else None
            current = initial_rates[si][metric]
            same_month = (
                si > 0
                and str(weekly[si - 1]["selected_cutoff_date"])[:7] == month
            )
            cache = (
                current - previous if same_month and current is not None
                and previous is not None else "#N/A"
            )
            calc.write_formula(
                idx, col,
                f'=IF(B{r}=B{r-1},{pct_col}{r}-{pct_col}{r-1},NA())'
                if si else "=NA()",
                pp, cache,
            )
        for month_of_series, metric, col in series:
            metric_col = ("F", "G", "H")[metric]
            cached = (
                initial_rates[si][metric] if month_of_series == month
                and metric == 0 and initial_rates[si][metric] is not None
                else "#N/A"
            )
            calc.write_formula(
                idx, col,
                f'=IF(AND($B{r}="{month_of_series}",$I{r}=1,'
                f'OR(Resumen!$A$6="Comparar las tres",'
                f'Resumen!$A$6="{INDICATORS[metric]}")),'
                f'IFERROR({metric_col}{r},NA()),NA())',
                percent, cached,
            )

    last = max(11, len(weekly) + 10)
    for col, data_col, diff_col in (("A", "F", "J"), ("H", "G", "K"),
                                    ("O", "H", "L")):
        source = f"'Tendencia - datos'!{data_col}11:{data_col}{last}"
        diffs = f"'Tendencia - datos'!{diff_col}11:{diff_col}{last}"
        condition = f"'Tendencia - datos'!I11:I{last}=1"
        metric = {"A": 0, "H": 1, "O": 2}[col]
        current = initial_rates[-1][metric] if initial_rates else None
        previous = initial_rates[-2][metric] if len(initial_rates) > 1 else None
        same_month = (
            len(weekly) > 1
            and str(weekly[-1]["selected_cutoff_date"])[:7]
            == str(weekly[-2]["selected_cutoff_date"])[:7]
        )
        delta_cache = (
            100 * (current - previous)
            if same_month and current is not None and previous is not None else ""
        )
        panel.write_formula(
            col + "10", f'=IFERROR(LOOKUP(2,1/({condition}),{source}),"")',
            big_pct, current if current is not None else ""
        )
        panel.write_formula(
            col + "12", f'=IFERROR(LOOKUP(2,1/({condition}),{diffs})*100,"")',
            pp, delta_cache
        )
    # La descripción sigue el último lunes del periodo seleccionado.
    condition = f"'Tendencia - datos'!I11:I{last}=1"
    date_source = f"'Tendencia - datos'!A11:A{last}"
    cutoff_formula = 'LOOKUP(2,1/(' + condition + '),' + date_source + ')'
    cutoff_label = (
        'DAY(' + cutoff_formula + ')&"/"&'
        'RIGHT("0"&MONTH(' + cutoff_formula + '),2)&"/"&'
        'YEAR(' + cutoff_formula + ')'
    )
    panel.write_formula(
        "A8",
        '=IFERROR("Corte actual: "&' + cutoff_label
        + '&"  ·  Ámbito: "&$K$6'
        + '&"  ·  "&COUNTIF(\'Tendencia - datos\'!I11:I'
        + str(last) + ',1)&" cortes disponibles",'
        + '"Sin lunes completos en el periodo seleccionado")',
        small,
        ("Corte actual: " + date.fromisoformat(
            str(weekly[-1]["selected_cutoff_date"])
        ).strftime("%d/%m/%Y")
         + " · Ámbito: " + scope_labels[0][0] + " · "
         + str(sum(
             1 for snap in weekly
             if str(snap["selected_cutoff_date"])[:7] >=
             f"{int(last_month[:4]) - (int(last_month[5:]) <= 2)}-"
             f"{((int(last_month[5:]) - 3) % 12) + 1:02d}"
         )) + " cortes disponibles")
        if weekly else "Sin lunes completos en el periodo seleccionado",
    )
    if weekly:
        chart = book.add_chart({"type": "line"})
        for month, metric, col in series:
            # XlsxWriter cachea por defecto NA() y celdas ausentes como 0.
            # Darle el cache explícito con None deja huecos reales en el gráfico.
            # La fórmula sigue viva para filtrar Periodo, Ámbito e Indicador.
            visible_points = [
                initial_rates[index][metric]
                if str(snapshot["selected_cutoff_date"])[:7] == month
                and metric == 0
                else None
                for index, snapshot in enumerate(weekly)
            ]
            chart.add_series({
                "name": INDICATORS[metric] + " · " + month,
                "categories": ["Tendencia - datos", 10, 0, last - 1, 0],
                "values": ["Tendencia - datos", 10, col, last - 1, col],
                "values_data": visible_points,
                "line": {"color": COLORS[metric], "width": 2.5},
                "marker": {"type": "circle", "size": 3},
            })
        chart.set_title({"name": "Evolución de conversiones (%)"})
        chart.set_y_axis({"num_format": "0%", "min": 0,
                          "major_gridlines": {"visible": True}})
        chart.set_x_axis({"date_axis": True, "num_format": "dd mmm"})
        chart.set_legend({"none": True})
        chart.show_blanks_as("gap")
        chart.show_hidden_data()
        chart.set_size({"width": 1190, "height": 490})
        panel.insert_chart("A14", chart)
        for cell, metric, color in (("B40", INDICATORS[0], COLORS[0]),
                                    ("I40", INDICATORS[1], COLORS[1]),
                                    ("P40", INDICATORS[2], COLORS[2])):
            fmt = book.add_format({"font_color": color, "bold": True})
            panel.write_string(cell, "● " + metric, fmt)
    else:
        panel.merge_range("A15:U17", "Sin lunes completos disponibles.", soft)

    # Dos pestañas visibles: Resumen y reporte operativo Original.
    write_original_operational_sheet(book, daily, scope_options, is_global=is_global)
    data.hide()
    calc.hide()
    panel.activate()

    book.close()
    return stream.getvalue()
