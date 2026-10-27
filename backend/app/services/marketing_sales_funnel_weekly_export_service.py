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
    catalog_date = xl_col_to_name(catalog_col + 3)
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
    # Excel almacena fecha real (primer día del mes); solo la presentación
    # cambia a "agosto-26". yy evita la máscara de fórmula yyyy/aaaa.
    month_choice = book.add_format({
        "bg_color": "#D8F8E9", "font_color": "#145C4A", "bold": True,
        "align": "center", "num_format": "[$-es-MX]mmmm-yy",
    })
    manual_inactive = book.add_format({
        "bg_color": "#FFFFFF", "font_color": "#FFFFFF",
        "num_format": "[$-es-MX]mmmm-yy",
    })
    manual_heading_inactive = book.add_format({
        "bg_color": "#FFFFFF", "font_color": "#FFFFFF",
    })
    manual_warning = book.add_format({
        "font_size": 9, "font_color": "#A33139",
    })
    card_backgrounds = ("#E8F0FC", "#F9DEDF", "#EAF3DF")
    card_text_colors = ("#204A91", "#A84149", "#416E29")
    def monthly_card_format(metric: int, kind: str, *, top=False,
                            bottom=False, left=False, right=False):
        """Contorno de cada tarjeta separado por indicador (filas 10-11)."""
        opts = {
            "bg_color": card_backgrounds[metric],
            "font_color": card_text_colors[metric],
            "align": "center", "valign": "vcenter",
            "border_color": "#34455E",
        }
        if kind == "rate":
            opts.update({"bold": True, "font_size": 13,
                         "num_format": "0.0%"})
        elif kind == "month":
            opts.update({"font_size": 9})
        elif kind == "arrow":
            opts.update({"font_size": 15, "bold": True})
        if top:
            opts["top"] = 2
        if bottom:
            opts["bottom"] = 2
        if left:
            opts["left"] = 2
        if right:
            opts["right"] = 2
        return book.add_format(opts)

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
                          ("K5:O5", "REGIÓN / SUCURSAL")):
        panel.merge_range(merged, title, navy)
    for area, value in (("A4:E4", PERIODS[0]),
                        ("A6:E6", INDICATORS[0]),
                        ("K6:O6", scope_labels[0][0])):
        panel.merge_range(area, value, choice)
    # Dos salidas calculadas: Desde/Hasta siempre son el rango EFECTIVO.
    # En XLSX sin macros una celda no puede ser fórmula y desplegable editable
    # a la vez, por eso Personalizado usa P4 y S4 como entradas independientes.
    # Los campos manuales se resaltan únicamente cuando corresponde usarlos.
    last_ym_date = date(int(last_month[:4]), int(last_month[5:7]), 1)
    first_custom_date = date(int(first_month[:4]), int(first_month[5:7]), 1)
    month_number = last_ym_date.year * 12 + last_ym_date.month - 3
    first_preset_date = date(month_number // 12, month_number % 12 + 1, 1)
    def serial(day: date) -> int:
        return (day - date(1899, 12, 30)).days

    panel.merge_range("P3:R3", "", manual_heading_inactive)
    panel.merge_range("S3:U3", "", manual_heading_inactive)
    panel.write_formula(
        "P3", '=IF($A$4="Personalizado","DESDE MANUAL","")',
        manual_heading_inactive, "",
    )
    panel.write_formula(
        "S3", '=IF($A$4="Personalizado","HASTA MANUAL","")',
        manual_heading_inactive, "",
    )
    for cell, span, value in (
        ("P4", "P4:R4", first_custom_date),
        ("S4", "S4:U4", last_ym_date),
    ):
        panel.merge_range(span, "", month_choice)
        panel.write_datetime(
            cell, datetime(value.year, value.month, 1), month_choice
        )
    # Fuera de Personalizado, las entradas no muestran valores ni encabezados.
    for manual_range in ("P4:R4", "S4:U4"):
        panel.conditional_format(manual_range, {
            "type": "formula", "criteria": '=$A$4<>"Personalizado"',
            "format": manual_inactive,
        })
    for manual_range in ("P3:R3", "S3:U3"):
        panel.conditional_format(manual_range, {
            "type": "formula", "criteria": '=$A$4="Personalizado"',
            "format": navy,
        })
    panel.merge_range("P5:U5", "", manual_warning)
    panel.write_formula(
        "P5",
        '=IF(AND($A$4="Personalizado",$P$4>$S$4),'
        '"Desde debe ser anterior o igual a Hasta","")',
        manual_warning, "",
    )
    for cell, span in (("F4", "F4:J4"), ("K4", "K4:O4")):
        panel.merge_range(span, "", month_choice)

    latest_year_month = "'Tendencia - datos'!$R$2"
    last_date_formula = (
        'DATE(VALUE(LEFT(' + latest_year_month + ',4)),'
        'VALUE(RIGHT(' + latest_year_month + ',2)),1)'
    )
    month_date_range = (
        f"'Tendencia - datos'!${catalog_date}$2:"
        f"${catalog_date}${max(2, len(months) + 1)}"
    )
    first_preset_formula = (
        '=IF($A$4="Personalizado",$P$4,'
        'IF($A$4="Todo el histórico",MIN(' + month_date_range + '),'
        'EDATE(' + last_date_formula + ',-'
        'IF($A$4="Últimos 3 meses",2,'
        'IF($A$4="Últimos 6 meses",5,11)))))'
    )
    last_preset_formula = (
        '=IF($A$4="Personalizado",$S$4,' + last_date_formula + ')'
    )
    panel.write_formula(
        "F4", first_preset_formula, month_choice, serial(first_preset_date)
    )
    panel.write_formula(
        "K4", last_preset_formula, month_choice, serial(last_ym_date)
    )
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
        "='Tendencia - datos'!$" + catalog_date + "$2:$"
        + catalog_date + "$" + str(max(2, len(months) + 1)),
    )
    panel.data_validation("K6", {"validate": "list", "source": "=FunnelAmbitos"})
    for cell in ("P4", "S4"):
        panel.data_validation(cell, {
            "validate": "list", "source": "=FunnelMeses",
            "input_title": "Rango personalizado",
            "input_message": "Se utiliza cuando Periodo es Personalizado.",
            "error_title": "Mes no disponible",
            "error_message": "Elige un mes del catálogo.",
        })
    # Eliminar nota redundante A7; no desplazar las referencias de celdas.
    panel.set_row(6, 6)
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
    for metric, (first, middle, latest, arrows, span) in enumerate((
        ("A", "D", "G", ("C", "F"), ("A", "G")),
        ("H", "K", "N", ("J", "M"), ("H", "N")),
        ("O", "R", "U", ("Q", "T"), ("O", "U")),
    )):
        first_end = xl_col_to_name(ord(first) - 64)
        middle_end = xl_col_to_name(ord(middle) - 64)
        for col, end_col, is_first in (
            (first, first_end, True), (middle, middle_end, False)
        ):
            panel.merge_range(
                f"{col}10:{end_col}10", "",
                monthly_card_format(metric, "month", top=True, left=is_first)
            )
            panel.merge_range(
                f"{col}11:{end_col}11", "",
                monthly_card_format(metric, "rate", bottom=True, left=is_first)
            )
        panel.write_blank(
            f"{latest}10", None,
            monthly_card_format(metric, "month", top=True, right=True)
        )
        panel.write_blank(
            f"{latest}11", None,
            monthly_card_format(metric, "rate", bottom=True, right=True)
        )
        for arrow in arrows:
            panel.write_blank(
                f"{arrow}10", None,
                monthly_card_format(metric, "empty", top=True)
            )
            panel.write_blank(
                f"{arrow}11", None,
                monthly_card_format(metric, "arrow", bottom=True)
            )
        panel.merge_range(f"{span[0]}12:{span[1]}12", "", pp)
        panel.merge_range(
            f"{span[0]}13:{span[1]}13", "", monthly_caption
        )

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
        catalog_name + ":" + catalog_date, 30, None, {"hidden": True}
    )
    for i, (text, key) in enumerate(scope_labels, 1):
        calc.write_string(i, catalog_col, text)
        calc.write_string(i, catalog_col + 1, key)
    for i, month in enumerate(months or [last_month], 1):
        calc.write_string(i, catalog_col + 2, month)
        calc.write_datetime(
            i, catalog_col + 3,
            datetime(int(month[:4]), int(month[5:7]), 1),
            month_choice,
        )
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
    # Fechas efectivas visibles en Resumen (F4/K4) son la única verdad.
    # Convertir fechas Excel a claves YYYY-MM sin máscaras dependientes
    # del idioma: la selección de periodo, mes y ámbito permanece cruzada.
    for target, address, initial in (
        ("S3", "F4", first_preset_date.strftime("%Y-%m")),
        ("S4", "K4", last_month),
    ):
        field = "Resumen!$" + address[0] + "$4"
        formula = (
            '=IFERROR(YEAR(' + field + ')&"-"&'
            'RIGHT("0"&MONTH(' + field + '),2),"")'
        )
        calc.write_formula(target, formula, None, initial)
    calc.write("R4", "Hasta efectivo", navy)
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

    # Tarjetas: último corte DISPONIBLE de cada uno de los tres meses
    # seleccionados, sobre las sumas de las sucursales autorizadas.
    # Nunca se promedian tasas de sucursales ni de semanas.
    last = max(11, len(weekly) + 10)
    month_names = ("Ene", "Feb", "Mar", "Abr", "May", "Jun",
                   "Jul", "Ago", "Sep", "Oct", "Nov", "Dic")
    month_excel_names = ",".join(f'"{name}"' for name in month_names)
    month_data_range = f"'Tendencia - datos'!$B$11:$B${last}"
    included_range = f"'Tendencia - datos'!$I$11:$I${last}"
    for (month_cells, arrow_cells, middle_cell, recent_cell,
         card_span, metric) in (
        (("A", "D", "G"), ("C", "F"), "D", "G", ("A", "G"), 0),
        (("H", "K", "N"), ("J", "M"), "K", "N", ("H", "N"), 1),
        (("O", "R", "U"), ("Q", "T"), "R", "U", ("O", "U"), 2),
    ):
        metric_col = ("F", "G", "H")[metric]
        rates_range = (
            f"'Tendencia - datos'!${metric_col}$11:"
            f"${metric_col}${last}"
        )
        last_values = []
        for key, card_col in zip(("T", "U", "V"), month_cells):
            selected_key = f"'Tendencia - datos'!${key}$2"
            month_label = (
                f"CHOOSE(VALUE(RIGHT({selected_key},2)),{month_excel_names})"
            )
            label_formula = (
                f'=IF({selected_key}="","",'
                f'{month_label}&" "&LEFT({selected_key},4))'
            )
            slot = ("T", "U", "V").index(key)
            month_value = initial_month_keys[slot]
            label_cache = (
                f"{month_names[int(month_value[5:7]) - 1]} {month_value[:4]}"
                if month_value else ""
            )
            panel.write_formula(
                f"{card_col}10", label_formula,
                monthly_card_format(metric, "month", top=True,
                                    left=(card_col == month_cells[0]),
                                    right=(card_col == month_cells[2])),
                label_cache
            )
            value_formula = (
                f'=IF({selected_key}="","",IFERROR(LOOKUP(2,1/'
                f'(({month_data_range}={selected_key})*'
                f'({included_range}=1)),{rates_range}),""))'
            )
            value_cache = next(
                (initial_rates[i][metric]
                 for i in range(len(weekly) - 1, -1, -1)
                 if str(weekly[i]["selected_cutoff_date"])[:7] == month_value),
                None,
            ) if month_value else None
            panel.write_formula(
                f"{card_col}11", value_formula,
                monthly_card_format(metric, "rate", bottom=True,
                                    left=(card_col == month_cells[0]),
                                    right=(card_col == month_cells[2])),
                value_cache if value_cache is not None else ""
            )
            last_values.append(value_cache)
        for arrow_cell, older, newer in (
            (arrow_cells[0], "T", "U"),
            (arrow_cells[1], "U", "V"),
        ):
            older_ref = f"'Tendencia - datos'!${older}$2"
            newer_ref = f"'Tendencia - datos'!${newer}$2"
            panel.write_formula(
                f"{arrow_cell}11",
                f'=IF(AND({older_ref}<>"",{newer_ref}<>""),"→","")',
                monthly_card_format(metric, "arrow", bottom=True),
                "→" if initial_month_keys[("T", "U", "V").index(older)]
                and initial_month_keys[("T", "U", "V").index(newer)] else "",
            )

        earlier_ref = "'Tendencia - datos'!$U$2"
        recent_ref = "'Tendencia - datos'!$V$2"
        delta_formula = (
            f'=IF(OR({earlier_ref}="",{recent_ref}=""),"",'
            f'IFERROR(({recent_cell}11-{middle_cell}11)*100,""))'
        )
        delta_cache = (
            100 * (last_values[2] - last_values[1])
            if initial_month_keys[1] and initial_month_keys[2]
            and last_values[1] is not None and last_values[2] is not None
            else ""
        )
        panel.write_formula(
            f"{card_span[0]}12", delta_formula, pp, delta_cache
        )
        prev_name = f"CHOOSE(VALUE(RIGHT({earlier_ref},2)),{month_excel_names})"
        latest_name = f"CHOOSE(VALUE(RIGHT({recent_ref},2)),{month_excel_names})"
        caption_formula = (
            f'=IF(OR({earlier_ref}="",{recent_ref}=""),'
            f'"Sin comparación mensual",'
            f'{prev_name}&" → "&{latest_name}&" · último corte de cada mes")'
        )
        caption_cache = (
            f"{month_names[int(initial_month_keys[1][5:7]) - 1]} → "
            f"{month_names[int(initial_month_keys[2][5:7]) - 1]}"
            " · último corte de cada mes"
            if initial_month_keys[1] and initial_month_keys[2]
            else "Sin comparación mensual"
        )
        panel.write_formula(
            f"{card_span[0]}13", caption_formula,
            monthly_caption, caption_cache
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
                "data_labels": {
                    "value": True, "num_format": "0.0%",
                    "position": "above", "font": {"size": 8},
                },
            })
        chart.set_title({"name": "Evolución de conversiones (%)"})
        chart.set_y_axis({"num_format": "0%", "min": 0,
                          "major_gridlines": {"visible": True}})
        chart.set_x_axis({"date_axis": True, "num_format": "dd mmm"})
        chart.set_legend({"none": True})
        chart.show_blanks_as("gap")
        chart.show_hidden_data()
        chart.set_size({"width": 1190, "height": 490})
        panel.insert_chart("A16", chart)
        for cell, metric, color in (("B44", INDICATORS[0], COLORS[0]),
                                    ("I44", INDICATORS[1], COLORS[1]),
                                    ("P44", INDICATORS[2], COLORS[2])):
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
