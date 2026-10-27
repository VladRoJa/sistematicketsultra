"""Hoja operativa original (paridad con marketing-sales-funnel-table-export.ts).

No cambia el origen de los datos: recibe el payload del Funnel Original
que ya está filtrado por MarketingAccess. Las tasas son ratios de totales,
nunca promedios de porcentajes.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from xlsxwriter.utility import xl_col_to_name

REGIONS = (
    ("REGIÓN MEXICALI BC", (1, 2, 3, 4, 5, 6)),
    ("REGIÓN COSTA BC", (7, 8, 9, 10, 11, 12, 13)),
    ("REGIÓN CLN / LA PAZ", (14, 15, 16, 20)),
    ("REGIÓN NORESTE", (17, 18, 24, 26)),
    ("REGIÓN CENTRO", (19, 21, 22, 23, 25)),
)
HEADERS = (
    "Sucursal", "Leads", "Visitantes totales", "Ventas digitales",
    "Ventas digitales orgánicas", "Venta web", "Venta BTL", "Ventas totales",
    "Lead → visita", "Visita → venta digital", "Lead → venta", "Inversión",
    "Ingreso digital", "Ingreso web", "Ingreso BTL", "Ingreso total",
    "Costo por lead (CPL)", "Costo por visita (CPT)", "Costo por venta (CAC)",
)
VALUES = {
    1: "leads_meta", 2: "visits_total", 3: "sales_digital",
    4: "sales_digital_organic", 5: "sales_web", 6: "sales_btl",
    11: "investment", 12: "revenue_digital", 13: "revenue_web",
    14: "revenue_btl",
}
MONTHS = (
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
)


def _n(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _sum_known(items: Sequence[Mapping[str, Any]], key: str) -> float | None:
    values = [_n(item.get(key)) for item in items]
    if any(item is None for item in values):
        return None
    return sum(v for v in values if v is not None)


def _sum_optional(items: Sequence[Mapping[str, Any]], key: str) -> float | None:
    values = [_n(item.get(key)) for item in items]
    available = [v for v in values if v is not None]
    return sum(available) if available else None


def _ratio(n: float | None, d: float | None) -> float | str:
    return n / d if n is not None and d is not None and d > 0 else ""


def write_original_operational_sheet(
    book: Any,
    daily: Mapping[str, Any],
    scope_options: Sequence[Mapping[str, Any]],
    *,
    is_global: bool,
) -> str:
    """Produce la hoja anterior completa; devolver su nombre para QA."""
    cutoff = date.fromisoformat(str(daily["selected_cutoff_date"]))
    title = f"{MONTHS[cutoff.month - 1]} {cutoff.year}"
    visible_names = {int(b["sucursal_id"]): str(b.get("sucursal") or "")
                     for b in scope_options}
    all_branches = [b for b in daily.get("branches", [])
                    if int(b["sucursal_id"]) in visible_names]
    by_id = {int(b["sucursal_id"]): b for b in all_branches}
    if is_global and len(by_id) == len(visible_names):
        scope = "Todo Ultra"
    elif len(by_id) == 1:
        scope = str(next(iter(by_id.values())).get("sucursal") or "Sucursal")
    else:
        scope = "Sucursales autorizadas"

    sheet = book.add_worksheet(title)
    sheet.set_tab_color("#233B60")
    sheet.hide_gridlines(2)
    sheet.freeze_panes(4, 1)
    sheet.set_landscape()
    sheet.fit_to_pages(1, 0)
    sheet.set_default_row(15)
    widths = (28, 12, 13, 18, 20, 12, 12, 14, 16, 19,
              12.2, 15, 14.2, 17, 14, 14, 16, 17, 17)
    for col, width in enumerate(widths):
        sheet.set_column(col, col, width)
    # Igual que ExcelJS: columnas de categorías y de ingreso desglosado plegadas.
    sheet.set_column("E:H", None, None, {"hidden": True, "level": 1})
    sheet.set_column("M:P", None, None, {"hidden": True, "level": 1})

    navy = "#1F2937"
    slate = "#374151"
    border = "#D1D5DB"
    common = {"font_name": "Calibri", "font_size": 10,
              "font_color": "#111827", "valign": "vcenter",
              "border": 1, "border_color": border}
    title_fmt = book.add_format({"font_name": "Calibri", "font_size": 16,
                                 "bold": True, "bg_color": navy,
                                 "font_color": "white", "valign": "vcenter"})
    subtitle_fmt = book.add_format({"font_name": "Calibri", "font_size": 10,
                                    "italic": True, "font_color": "#6B7280"})
    header_fmt = book.add_format({"font_name": "Calibri", "font_size": 9,
                                  "bold": True, "bg_color": slate,
                                  "font_color": "white", "align": "center",
                                  "valign": "vcenter", "text_wrap": True,
                                  "border": 1, "border_color": border})
    region_fmt = book.add_format({"bg_color": "#E5E7EB",
                                  "font_color": "#111827", "bold": True,
                                  "font_name": "Calibri", "font_size": 10})
    fmts = {}
    for variant, fill in (("regular", None), ("subtotal", "#F3F4F6"),
                          ("total", "#E8EEF7")):
        for col in range(19):
            p = dict(common)
            p["align"] = "left" if col == 0 else "right"
            p["text_wrap"] = col == 0
            if col == 0 or variant != "regular":
                p["bold"] = True
            if fill:
                p["bg_color"] = fill
            if 8 <= col <= 10:
                p["num_format"] = "0.0%"
            elif col in (1, 2, 3, 4, 5, 6, 7):
                p["num_format"] = "#,##0"
            elif col >= 11:
                p["num_format"] = '$#,##0.00;[Red]-$#,##0.00'
            fmts[variant, col] = book.add_format(p)
    commercial_head = book.add_format({"bg_color": navy, "font_color": "white",
                                       "bold": True, "font_name": "Calibri"})
    commercial_label = book.add_format({"font_name": "Calibri", "font_size": 10,
                                        "border": 1, "border_color": border})
    commercial_int = book.add_format({"num_format": "#,##0",
                                      "border": 1, "border_color": border})
    commercial_currency = book.add_format({"num_format": '$#,##0.00',
                                           "border": 1, "border_color": border})
    commercial_pct = book.add_format({"num_format": "0.0%",
                                      "border": 1, "border_color": border})
    highlighted = book.add_format({"bg_color": "#FFFF00", "bold": True,
                                    "num_format": "#,##0", "border": 1,
                                    "border_color": border})
    cf_bad = book.add_format({"bg_color": "#FFC7CE", "font_color": "#9C0006"})
    cf_good = book.add_format({"bg_color": "#C6EFCE", "font_color": "#006100"})

    sheet.set_row(0, 24)
    sheet.set_row(1, 18)
    sheet.set_row(2, 8)
    sheet.set_row(3, 31)
    sheet.merge_range("A1:S1", "FUNNEL DE VENTA NUEVA · DETALLE POR SUCURSAL", title_fmt)
    sheet.merge_range("A2:S2", f"{title} · Alcance: {scope}", subtitle_fmt)
    for col, value in enumerate(HEADERS):
        sheet.write(3, col, value, header_fmt)

    def write_cell(r: int, col: int, value: Any, variant: str) -> None:
        fmt = fmts[variant, col]
        if value is None:
            sheet.write_blank(r, col, None, fmt)
        else:
            sheet.write(r, col, value, fmt)

    def write_formula(r: int, col: int, formula: str, cached: Any, variant: str) -> None:
        if cached is None:
            cached = ""
        sheet.write_formula(r, col, formula, fmts[variant, col], cached)

    def totals_of(items: Sequence[Mapping[str, Any]]) -> dict[int, float | None]:
        d = {col: _sum_known(items, key) for col, key in VALUES.items()}
        d[11] = _sum_optional(items, "investment")
        d[7] = sum((_n(x.get("sales_total")) or 0) for x in items)
        d[15] = sum((_n(x.get("revenue_total")) or 0) for x in items)
        return d

    def write_ratios(r: int, d: Mapping[int, float | None], variant: str) -> None:
        x = r + 1
        for col, formula, cached in (
            (8, f'=IF(OR(B{x}="",B{x}=0),"",C{x}/B{x})', _ratio(d.get(2), d.get(1))),
            (9, f'=IF(OR(D{x}="",C{x}=0),"",D{x}/C{x})', _ratio(d.get(3), d.get(2))),
            (10, f'=IF(OR(D{x}="",B{x}="",B{x}=0),"",D{x}/B{x})', _ratio(d.get(3), d.get(1))),
            (16, f'=IF(OR(L{x}="",B{x}=0),"",L{x}/B{x})', _ratio(d.get(11), d.get(1))),
            (17, f'=IF(OR(L{x}="",C{x}=0),"",L{x}/C{x})', _ratio(d.get(11), d.get(2))),
            (18, f'=IF(OR(L{x}="",D{x}+E{x}=0),"",L{x}/(D{x}+E{x}))',
             _ratio(d.get(11), (d.get(3) or 0) + (d.get(4) or 0))
             if d.get(3) is not None and d.get(4) is not None else ""),
        ):
            write_formula(r, col, formula, cached, variant)

    def write_branch(r: int, b: Mapping[str, Any]) -> None:
        write_cell(r, 0, str(b.get("sucursal") or ""), "regular")
        d = totals_of([b])
        for col in VALUES:
            write_cell(r, col, d[col], "regular")
        row = r + 1
        write_formula(r, 7, f"=SUM(D{row}:G{row})", d[7], "regular")
        write_formula(r, 15, f"=SUM(M{row}:O{row})", d[15], "regular")
        # En el Excel anterior las celdas I:K y Q:S muestran las mismas fórmulas.
        write_formula(r, 8, f'=IFERROR(C{row}/B{row},"")', _ratio(d[2], d[1]), "regular")
        write_formula(r, 9, f'=IFERROR(D{row}/C{row},"")', _ratio(d[3], d[2]), "regular")
        write_formula(r, 10, f'=IFERROR(D{row}/B{row},"")', _ratio(d[3], d[1]), "regular")
        investment = d[11]
        for col, formula, cache in (
            (16, f'=IF(OR(L{row}="",B{row}="",B{row}=0),"",L{row}/B{row})',
             _ratio(investment, d[1])),
            (17, f'=IF(OR(L{row}="",C{row}=0),"",L{row}/C{row})',
             _ratio(investment, d[2])),
            (18, f'=IF(OR(L{row}="",D{row}="",D{row}+E{row}=0),"",L{row}/(D{row}+E{row}))',
             _ratio(investment, (d[3] or 0) + (d[4] or 0))
             if d[3] is not None and d[4] is not None else ""),
        ):
            write_formula(r, col, formula, cache, "regular")

    row = 4  # row indices are zero-based; Excel row 5 is the first region.
    subtotals: list[int] = []
    for region_name, ids in (*REGIONS, ("OTRAS SUCURSALES", ())):
        if ids:
            members = [by_id[bid] for bid in ids if bid in by_id]
        else:
            known = {x for _, ids_ in REGIONS for x in ids_}
            members = sorted((b for bid, b in by_id.items() if bid not in known),
                             key=lambda b: str(b.get("sucursal", "")).lower())
        if not members:
            continue
        sheet.set_row(row, 18)
        sheet.write(row, 0, region_name, region_fmt)
        row += 1
        start = row
        for b in members:
            write_branch(row, b)
            row += 1
        end = row
        sums = totals_of(members)
        sheet.set_row(row, 18)
        write_cell(row, 0, "SUBTOTAL REGIÓN", "subtotal")
        for col in (*range(1, 8), *range(11, 16)):
            key = xl_col_to_name(col)
            cached = sums.get(col)
            if col == 7:
                cached = sums[7]
            if col == 15:
                cached = sums[15]
            formula = f'=SUM({key}{start+1}:{key}{end})'
            if cached is None:
                formula = f'=IF(COUNT({key}{start+1}:{key}{end})=0,"",SUM({key}{start+1}:{key}{end}))'
            write_formula(row, col, formula, cached, "subtotal")
        write_ratios(row, sums, "subtotal")
        subtotals.append(row)
        for target, bad, good in (("I", 0.15, 0.15), ("J", 0.30, 0.30),
                                  ("K", 0.05, 0.05)):
            region_rng = f"{target}{start+1}:{target}{row+1}"
            sheet.conditional_format(region_rng, {"type": "cell", "criteria": "<",
                                                   "value": bad, "format": cf_bad})
            sheet.conditional_format(region_rng, {"type": "cell", "criteria": ">=",
                                                   "value": good, "format": cf_good})
        row += 1
        sheet.set_row(row, 8)
        row += 1

    total_idx = row + 1  # mantener la fila en blanco antes de TOTAL
    sheet.set_row(total_idx, 20)
    write_cell(total_idx, 0, "TOTAL", "total")
    all_totals = totals_of(all_branches)
    for col in (*range(1, 8), *range(12, 16)):
        key = xl_col_to_name(col)
        formula = "=" + "+".join(f"{key}{r+1}" for r in subtotals) if subtotals else "=0"
        write_formula(total_idx, col, formula, all_totals.get(col), "total")
    for col in (7, 15):
        key = xl_col_to_name(col)
        formula = "=" + "+".join(f"{key}{r+1}" for r in subtotals) if subtotals else "=0"
        write_formula(total_idx, col, formula, all_totals.get(col), "total")
    write_cell(total_idx, 11, all_totals.get(11), "total")
    write_ratios(total_idx, all_totals, "total")

    # Sección RESUMEN COMERCIAL de la descarga ExcelJS original.
    commercial_header_idx = total_idx + 3
    sheet.set_row(commercial_header_idx, 18)
    for col in range(6):
        sheet.write_blank(commercial_header_idx, col, None, commercial_head)
    sheet.write(commercial_header_idx, 0, "RESUMEN COMERCIAL", commercial_head)
    total_r = commercial_header_idx + 1
    digital_r = total_r + 1
    other_r = total_r + 2
    investment_r = total_r + 3
    all_sales = all_totals[7] or 0
    digital_sales = ((all_totals.get(3) or 0) + (all_totals.get(4) or 0))
    other_sales = all_sales - digital_sales
    gap = digital_sales - all_sales * .5
    sheet.write(total_r, 0, "Total de ventas nuevas", commercial_label)
    sheet.write_formula(total_r, 1, f"=H{total_idx+1}", commercial_int, all_sales)
    sheet.write(total_r, 4, "Meta digital (50%)", commercial_label)
    sheet.write_formula(total_r, 5, f"=B{total_r+1}*0.5", commercial_int, all_sales * .5)
    sheet.write(digital_r, 0, "Ventas vía Digital", commercial_label)
    sheet.write_formula(digital_r, 1,
                        f'=IF(D{total_idx+1}="","",D{total_idx+1}+E{total_idx+1})',
                        commercial_int, digital_sales)
    sheet.write_formula(digital_r, 2,
                        f'=IF(B{digital_r+1}="","",IFERROR(B{digital_r+1}/B{total_r+1},""))',
                        commercial_pct, _ratio(digital_sales, all_sales))
    sheet.write(digital_r, 4, "Brecha vs meta", commercial_label)
    sheet.write_formula(digital_r, 5, f'=IF(B{digital_r+1}="","",B{digital_r+1}-F{total_r+1})',
                        highlighted, gap)
    sheet.write(other_r, 0, "Ventas otros canales", commercial_label)
    sheet.write_formula(other_r, 1, f'=IF(B{digital_r+1}="","",B{total_r+1}-B{digital_r+1})',
                        commercial_int, other_sales)
    sheet.write_formula(other_r, 2,
                        f'=IF(B{other_r+1}="","",IFERROR(B{other_r+1}/B{total_r+1},""))',
                        commercial_pct, _ratio(other_sales, all_sales))
    sheet.write(investment_r, 0, "Inversión", commercial_label)
    sheet.write_formula(investment_r, 1,
                        f'=IF(L{total_idx+1}="","",L{total_idx+1})',
                        commercial_currency,
                        all_totals[11] if all_totals[11] is not None else "")

    return title
