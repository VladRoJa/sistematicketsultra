"""Excel ejecutivo de rachas OBSERVADAS POR MES DE COMPRA en Gasca.

No se deben considerar PAGOS/VIGENCIAS verificadas. Usa los ID Socio
presentes en el padrón ACTIVO para separar universos; KPI=SI sólo se
incluye en la hoja Activos; los ID no presentes quedan como candidatos
históricos en Vencidos, con KPI DESCONOCIDO.

Ejemplo PowerShell desde backend:
.\.venv\\Scripts\\python.exe -m scripts.ops.export_member_streaks_presentation \\
  --active-xlsx "C:\\Users\\USER01\\Downloads\\Reporte Socios Activos.xlsx" \\
  --as-of 2026-11-07 \\
  --output "data\\backfill\\gasca_venta_total_enriched\\consolidated\\Propuesta_Rachas_Ultra.xlsx"

Requiere la SQLite local consolidada (no PostgreSQL ni credenciales).
"""
from __future__ import annotations

import argparse
import itertools
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterator
from zipfile import ZipFile

import xlsxwriter
from lxml import etree

from scripts.ops.consolidate_gasca_member_sales import (
    _cell_text, _column_number, _shared_strings,
    XML_NS,
)
from scripts.ops.profile_gasca_member_sales import DEFAULT_DATABASE


MONTH_START = "2020-01"
MONTH_END = "2026-10"  # El consolidado actual llega hasta octubre.
TIERS = ((1, 599), (4, 499), (7, 399), (10, 299))
HEADER = (
    "ID Socio", "Sucursal", "Nombre", "PIN", "Aplica KPI",
    "Ultimo pago", "Vencimiento", "Racha observada",
    "Inicio racha", "Fin racha", "Nivel tentativo",
    "Tarifa simulada", "Movimientos", "Meses con compra",
    "Calidad", "Observacion",
)


@dataclass(frozen=True)
class ActiveRow:
    member_id: str
    branch: str
    name: str
    pin: str
    kpi: str
    last_payment: str
    expires: str
    tarifa: str = ""


def _norm_id(raw: str) -> str:
    value = str(raw or "").strip()
    if re.fullmatch(r"\d+\.0+", value):
        return value.split(".")[0]
    return value


def _calendar_date(raw: str) -> str:
    value = str(raw or "").strip()
    for pattern in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d-%m-%y"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            pass
    return ""


def iter_active_xlsx(path: Path) -> Iterator[dict[str, str]]:
    """Extrae XLSX en streaming; preserva PIN como texto y no reserializa RAW."""
    expected = {
        "ID Socio", "Pin", "Nombre", "Sucursal", "Aplica KPI",
        "Fecha Último Pago", "Fecha Vencimiento", "Tarifa",
    }
    with ZipFile(path) as archive:
        shared = _shared_strings(archive)
        mapping: dict[str, int] = {}
        important: set[int] = set()
        with archive.open("xl/worksheets/sheet1.xml") as stream:
            for _, row in etree.iterparse(
                stream, events=("end",), tag=XML_NS + "row",
            ):
                cells = {
                    _column_number(cell.get("r", "")): _cell_text(cell, shared)
                    for cell in row.iterchildren(XML_NS + "c")
                    if not important or _column_number(cell.get("r", "")) in important
                }
                if not mapping:
                    headers = {value.strip(): col for col, value in cells.items()}
                    if expected.issubset(headers):
                        mapping = {name: headers[name] for name in expected}
                        important = set(mapping.values())
                    elif int(row.get("r") or 0) > 5:
                        raise ValueError("Encabezados de Socios Activos no encontrados.")
                elif cells.get(mapping["ID Socio"], "").strip():
                    yield {field: cells.get(col, "").strip()
                           for field, col in mapping.items()}
                row.clear()
                while row.getprevious() is not None:
                    del row.getparent()[0]
        if not mapping:
            raise ValueError("Reporte de Activos sin encabezados reconocidos.")


def load_active(path: Path) -> tuple[dict[str, ActiveRow], Counter]:
    if not path.is_file():
        raise FileNotFoundError(f"No existe reporte de Socios Activos: {path}")
    active: dict[str, ActiveRow] = {}
    counts = Counter()
    for row in iter_active_xlsx(path):
        member = _norm_id(row["ID Socio"])
        if not member:
            continue
        if member in active:
            raise ValueError(
                "Hay ID Socio duplicados en el reporte Activos. "
                "Resolverlos antes de separar universos."
            )
        kpi = row["Aplica KPI"].strip().upper()
        if kpi not in {"SI", "SÍ", "NO"}:
            kpi = "DESCONOCIDO"
        active[member] = ActiveRow(
            member, row["Sucursal"].upper(), row["Nombre"], row["Pin"],
            "SI" if kpi in {"SI", "SÍ"} else kpi,
            _calendar_date(row["Fecha Último Pago"]),
            _calendar_date(row["Fecha Vencimiento"]),
            row["Tarifa"],
        )
        counts["activos_en_archivo"] += 1
        counts["activos_kpi_si" if kpi in {"SI", "SÍ"} else "activos_excluidos_kpi"] += 1
    if not active:
        raise ValueError("No se encontraron ID Socio válidos en Activos.")
    return active, counts


def _month_number(value: str) -> int:
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
        raise ValueError(f"Mes de compra inválido: {value!r}")
    return int(value[:4]) * 12 + int(value[5:]) - 1


def _month_text(number: int) -> str:
    year, zero_based = divmod(number, 12)
    return f"{year:04d}-{zero_based+1:02d}"


def _best_run(months: set[int]) -> tuple[int, int | None, int | None]:
    length, start, best = 0, None, (0, None, None)
    last = None
    for month in sorted(months):
        if last is not None and month == last + 1:
            length += 1
        else:
            length, start = 1, month
        if length >= best[0]:
            best = (length, start, month)
        last = month
    return best


def _current_run(months: set[int], anchor: int) -> tuple[int, int | None, int | None]:
    if anchor not in months:
        return (0, None, None)
    current = anchor
    while current - 1 in months:
        current -= 1
    return (anchor - current + 1, current, anchor)


def _tier(streak: int) -> int | None:
    return (1 if streak < 4 else 2 if streak < 7 else 3 if streak < 10 else 4) if streak else None


def _source_months(database: sqlite3.Connection) -> set[str]:
    return {str(row[0]) for row in database.execute(
        "SELECT DISTINCT source_month FROM purchase_events"
    )}


def _months(start: str, end: str) -> list[str]:
    return [_month_text(m) for m in range(_month_number(start), _month_number(end) + 1)]


def _create_book(output: Path, months: list[str], source_gaps: set[str], as_of: date):
    output.parent.mkdir(parents=True, exist_ok=True)
    book = xlsxwriter.Workbook(
        str(output), {"constant_memory": True, "use_zip64": True, "strings_to_urls": False},
    )
    book.set_properties({
        "title": "Ultra Gym | Simulador BI de Rachas",
        "subject": "Propuesta exploratoria de permanencia",
        "comments": "Compras observadas NO equivalen a cobertura pagada.",
    })
    formats = {
        "title": book.add_format({"bold": True, "font_size": 17, "font_color": "#FFFFFF",
                                   "bg_color": "#193A5B", "valign": "vcenter"}),
        "sub": book.add_format({"font_color": "#5C6B7A", "font_size": 10}),
        "header": book.add_format({"bg_color": "#27557C", "font_color": "#FFFFFF",
                                    "bold": True, "text_wrap": True,
                                    "valign": "vcenter", "border": 0}),
        "gap_header": book.add_format({"bg_color": "#B7782F", "font_color": "#FFFFFF",
                                        "bold": True, "text_wrap": True}),
        "text": book.add_format({"font_color": "#283745"}),
        "light": book.add_format({"font_color": "#64748B"}),
        "integer": book.add_format({"num_format": "#,##0"}),
        "price": book.add_format({"num_format": '"$"#,##0.00'}),
        "month": book.add_format({"bg_color": "#D8EEE4", "font_color": "#17634E",
                                   "align": "center", "bold": True}),
        "level": book.add_format({"bg_color": "#E6F1FA", "font_color": "#174E78",
                                   "bold": True, "align": "center"}),
        "warning": book.add_format({"bg_color": "#FFF4DE", "font_color": "#835520"}),
        "kpi": book.add_format({"bg_color": "#193A5B", "font_color": "#FFFFFF", "bold": True,
                                 "font_size": 15}),
        "rule": book.add_format({"bg_color": "#EAF1F5", "bold": True,
                                  "font_color": "#193A5B"}),
        "bad": book.add_format({"bg_color": "#FBE8E5", "font_color": "#9F3830"}),
    }
    book.add_worksheet("Resumen")
    for label in ("Activos", "Vencidos"):
        sheet = book.add_worksheet(label)
        sheet.hide_gridlines(2)
        sheet.set_landscape()
        sheet.set_zoom(85)
        sheet.merge_range(0, 0, 0, 15, f"ULTRA GYM  |  {label.upper()} · Rachas de compras observadas", formats["title"])
        sheet.set_row(0, 31)
        sheet.merge_range(1, 0, 1, 15,
            f"Fecha del padrón: {as_of.isoformat()}  |  Corte ventas: {MONTH_END}  |  Niveles SOLO para simulación; no son pagos certificados.",
            formats["sub"])
        sheet.merge_range(2, 0, 2, 15,
            "Un 1 indica compra identificada en el mes, NO prueba un mes pagado. Naranja = mes sin fuente. Filtra por ID Socio o sucursal.",
            formats["sub"])
        sheet.set_row(3, 7)
        sheet.set_row(4, 32)
        sheet.write_row(4, 0, list(HEADER), formats["header"])
        for idx, month in enumerate(months, start=len(HEADER)):
            sheet.write_string(4, idx, month, formats["gap_header"] if month in source_gaps else formats["header"])
        sheet.freeze_panes(5, 4)
        for col, width in enumerate((15, 22, 34, 14, 12, 14, 14, 17, 13, 13, 16, 16, 14, 17, 23, 34)):
            sheet.set_column(col, col, width)
        sheet.set_column(len(HEADER), len(HEADER)+len(months)-1, 10)
    book.add_worksheet("Reglas")
    return book, formats


def _write_member(ws, rowno: int, *, member_id: str, branch: str, name: str,
                  pin: str, kpi: str, last_payment: str, expires: str,
                  rows: int, months_seen: set[int], source_gaps: set[str],
                  anchor: int, is_active: bool, styles: dict, month_index: dict):
    streak, begins, ends = (
        _current_run(months_seen, anchor) if is_active else _best_run(months_seen)
    )
    tier = _tier(streak)
    quality = "SOLO_COMPRAS_OBSERVADAS" if streak else "PENDIENTE_VALIDAR_VIGENCIA" if is_active else "SIN_COMPRA_ACTIVA"
    notes = (
        "Sin compra en mes de corte; revisar prepago, vigencia y noviembre."
        if is_active and not streak else
        "KPI histórico no disponible; validar antes de aprobación."
        if not is_active else
        "Nivel no certificable sin vigencias y conciliación."
    )
    if is_active and streak and source_gaps:
        notes = "Racha hasta el ultimo mes del historico; validar ciclo vigente."
    fields = [
        member_id, branch, name, pin, kpi, last_payment, expires, streak,
        _month_text(begins) if begins is not None else "",
        _month_text(ends) if ends is not None else "",
        tier or "", None, rows, len(months_seen), quality, notes,
    ]
    for col, value in enumerate(fields):
        if col in {7, 12, 13}:
            ws.write_number(rowno, col, int(value), styles["integer"])
        elif col == 10 and tier is not None:
            ws.write_number(rowno, col, tier, styles["level"])
        elif col == 11:
            if tier is not None:
                excel_row = rowno + 1
                ws.write_formula(
                    rowno, col,
                    f'=IF(K{excel_row}="","",INDEX(Reglas!$C$6:$C$9,K{excel_row}))',
                    styles["price"], TIERS[tier - 1][1],
                )
        else:
            ws.write_string(rowno, col, str(value or ""),
                            styles["warning"] if col == 14 else styles["text"])
    for month in sorted(months_seen):
        col = month_index.get(month)
        if col is not None:
            ws.write_number(rowno, col, 1, styles["month"])
    return tier, quality


def _stream_grouped(conn: sqlite3.Connection):
    cursor = conn.execute("""
        SELECT id_socio, source_month, tipo, estatus, sucursal
        FROM purchase_events ORDER BY id_socio, source_month
    """)
    for mid, rows in itertools.groupby(cursor, key=lambda r: _norm_id(r[0])):
        observed: set[int] = set()
        count, canceled, last_branch = 0, 0, ""
        for _, source_month, kind, status, branch in rows:
            count += 1
            last_branch = str(branch or "").upper() or last_branch
            if status == "ACTIVO":
                observed.add(_month_number(source_month))
            if status == "CANCELADO":
                canceled += 1
        yield mid, observed, count, canceled, last_branch


def generate(*, database: Path, active_xlsx: Path, output: Path,
             as_of: date, start_month: str = MONTH_START,
             end_month: str = MONTH_END, replace: bool = False) -> dict:
    if output.resolve() in {database.resolve(), active_xlsx.resolve()}:
        raise ValueError("La salida no puede sobrescribir los insumos.")
    if output.exists() and not replace:
        raise FileExistsError(
            f"El Excel ya existe: {output}. Usa otro nombre o --replace."
        )
    temp_output = output.with_name(output.stem + ".partial.xlsx")
    if temp_output.exists():
        raise FileExistsError(
            f"Hay una exportación parcial: {temp_output}. Revísala antes de repetir."
        )
    active, active_counts = load_active(active_xlsx)
    if not database.is_file():
        raise FileNotFoundError(f"No existe histórico local: {database}")
    months = _months(start_month, end_month)
    anchor = _month_number(end_month)
    conn = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        conn.execute("PRAGMA query_only = ON")
        source = _source_months(conn)
        gaps = set(months) - source
        if end_month not in source:
            raise ValueError("No hay fuente verificada del mes final solicitado.")
        book, styles = _create_book(temp_output, months, gaps, as_of)
        ws_a = book.get_worksheet_by_name("Activos")
        ws_v = book.get_worksheet_by_name("Vencidos")
        counters = Counter(active_counts)
        levels_active, levels_expired = Counter(), Counter()
        row_a = row_v = 5
        matched_active: set[str] = set()
        month_index = {_month_number(m): i+len(HEADER) for i, m in enumerate(months)}
        try:
            for mid, observed, n, cancel, branch in _stream_grouped(conn):
                person = active.get(mid)
                if person:
                    matched_active.add(mid)
                    if person.kpi != "SI":
                        continue
                    tier, quality = _write_member(
                        ws_a, row_a, member_id=mid, branch=person.branch,
                        name=person.name, pin=person.pin, kpi="SI",
                        last_payment=person.last_payment, expires=person.expires,
                        rows=n, months_seen=observed, source_gaps=gaps,
                        anchor=anchor, is_active=True, styles=styles,
                        month_index=month_index,
                    )
                    row_a += 1
                    counters["activos_con_ventas"] += 1
                    levels_active[tier or 0] += 1
                    if cancel:
                        counters["activos_con_cancelaciones_historicas"] += 1
                else:
                    tier, quality = _write_member(
                        ws_v, row_v, member_id=mid, branch=branch,
                        name="", pin="", kpi="NO DISPONIBLE",
                        last_payment="", expires="", rows=n,
                        months_seen=observed, source_gaps=gaps,
                        anchor=anchor, is_active=False, styles=styles,
                        month_index=month_index,
                    )
                    row_v += 1
                    counters["historicos_no_en_activos"] += 1
                    levels_expired[tier or 0] += 1
                    if cancel:
                        counters["historicos_con_cancelaciones"] += 1
            # Retener también Activos KPI=SI que no tienen un movimiento de
            # Venta Total identificable. No inventarles racha ni descuento.
            for mid, person in sorted(active.items()):
                if mid in matched_active or person.kpi != "SI":
                    continue
                tier, quality = _write_member(
                    ws_a, row_a, member_id=mid, branch=person.branch,
                    name=person.name, pin=person.pin, kpi="SI",
                    last_payment=person.last_payment, expires=person.expires,
                    rows=0, months_seen=set(), source_gaps=gaps,
                    anchor=anchor, is_active=True, styles=styles,
                    month_index=month_index,
                )
                row_a += 1
                counters["activos_sin_ventas_identificadas"] += 1
                levels_active[0] += 1
            for ws, last in ((ws_a, row_a), (ws_v, row_v)):
                ws.autofilter(4, 0, max(5,last - 1), len(HEADER)+len(months)-1)

            rules = book.get_worksheet_by_name("Reglas")
            rules.hide_gridlines(2)
            rules.set_column("A:A", 20)
            rules.set_column("B:C", 23)
            rules.set_column("E:E", 88)
            rules.merge_range("A1:F1", "ULTRA GYM  |  Reglas de simulación", styles["title"])
            rules.write("A3", "Inicio nivel", styles["rule"])
            rules.write("B3", "Nivel", styles["rule"])
            rules.write("C3", "Precio / mes (MXN)", styles["rule"])
            rules.write("E3", "Interpretación", styles["rule"])
            for idx, (threshold, price) in enumerate(TIERS, start=5):
                rules.write_number(idx, 0, threshold)
                rules.write_number(idx, 1, idx - 4)
                rules.write_number(idx, 2, price, styles["price"])
            rules.write("E5", "Precios editables. La tarifa individual usa esta tabla.")
            rules.write("E6", "El nivel viene de racha OBSERVADA; no equivale a mensualidades pagadas.")
            rules.write("E7", "Activos: meses de compra consecutivos terminando en el corte de Venta Total.")
            rules.write("E8", "Vencidos: mejor secuencia de meses de compra del histórico.")
            rules.write("E9", "KPI NO DISPONIBLE en históricos: no atribuir elegibilidad para descuentos.")
            rules.write("E10", "Rachas interrumpidas por 2020-04 a 2020-06 se consideran parciales.")
            rules.write("A12", "Corte ventas"); rules.write("B12", end_month)
            rules.write("A13", "Padrón activos"); rules.write("B13", as_of.isoformat())
            rules.write("A14", "Meses sin RAW"); rules.write("B14", ", ".join(sorted(gaps)))

            summary = book.get_worksheet_by_name("Resumen")
            summary.activate()
            summary.hide_gridlines(2)
            summary.set_column("A:A", 25)
            summary.set_column("B:D", 22)
            summary.set_column("F:F", 35)
            summary.set_column("G:G", 74)
            summary.merge_range("A1:G1", "ULTRA GYM  |  Propuesta de permanencia por rachas", styles["title"])
            summary.set_row(0, 32)
            summary.merge_range("A2:G2", f"Datos: Venta Total {start_month} a {end_month} | Activos al {as_of.isoformat()}", styles["sub"])
            summary.write("A4", "SOCIOS ACTIVOS KPI=SI", styles["rule"])
            summary.write_number("B4", counters["activos_kpi_si"], styles["kpi"])
            summary.write("A5", "HISTÓRICOS SIN ACTIVO", styles["rule"])
            summary.write_number("B5", counters["historicos_no_en_activos"], styles["kpi"])
            summary.write("A6", "ACTIVOS KPI EXCLUIDOS", styles["rule"])
            summary.write_number("B6", counters["activos_excluidos_kpi"], styles["integer"])
            summary.write("A7", "ACTIVOS PENDIENTES VALIDAR VIGENCIA", styles["rule"])
            summary.write_number("B7", levels_active[0], styles["integer"])
            summary.write("A8", "MESES SIN FUENTE", styles["rule"])
            summary.write_number("B8", len(gaps), styles["integer"])
            summary.write_row("A11", ["Nivel", "Racha observada", "Activos", "Vencidos", "Tarifa", "Potencial activos", "Potencial históricos"], styles["header"])
            for level, (threshold, price) in enumerate(TIERS, start=1):
                rr = 11 + level
                upper = (TIERS[level][0]-1) if level < 4 else "10+"
                summary.write_number(rr, 0, level, styles["level"])
                summary.write_string(rr, 1, f"{threshold} a {upper}" if level < 4 else "10+", styles["text"])
                summary.write_number(rr, 2, levels_active[level], styles["integer"])
                summary.write_number(rr, 3, levels_expired[level], styles["integer"])
                summary.write_formula(rr, 4, f"=Reglas!C{level+5}", styles["price"], price)
                summary.write_formula(rr, 5, f"=C{rr+1}*E{rr+1}", styles["price"], levels_active[level]*price)
                summary.write_formula(rr, 6, f"=D{rr+1}*E{rr+1}", styles["price"], levels_expired[level]*price)
            summary.write("A18", "SIN NIVEL TENTATIVO / REVISAR")
            summary.write_number("C18", levels_active[0], styles["integer"])
            summary.write_number("D18", levels_expired[0], styles["integer"])
            summary.merge_range("A21:G21", "LECTURA CORRECTA DEL SIMULADOR", styles["rule"])
            summary.write("A23", "1  Activos", styles["rule"])
            summary.merge_range("B23:G23", "Solo Aplica KPI=SI. Su racha se ancla al último mes disponible de Venta Total.")
            summary.write("A24", "2  Históricos", styles["rule"])
            summary.merge_range("B24:G24", "Todos los ID Socio de Venta Total que NO están en Activos. KPI histórico no disponible.")
            summary.write("A25", "3  Evidencia", styles["rule"])
            summary.merge_range("B25:G25", "Cada 1 mensual indica una compra observada, NO necesariamente un mes de servicio pagado.")
            summary.write("A26", "4  Próximo paso", styles["rule"])
            summary.merge_range("B26:G26", "Validar cobros y vigencias con Gasca antes de aplicar beneficios o asignar tarifas.")
            summary.write("A27", "5  Precaución", styles["rule"])
            summary.merge_range("B27:G27", "No contabilizar escenarios de históricos como KPI elegible sin validación posterior.")
            summary.write("A29", "Meses sin fuente", styles["rule"])
            summary.merge_range("B29:G29", ", ".join(sorted(gaps)) or "Ninguno")
            summary.freeze_panes(3, 0)

            output_count = counters["activos_con_ventas"] + counters["activos_sin_ventas_identificadas"]
            if output_count != counters["activos_kpi_si"]:
                raise AssertionError("Descuadre: falta un activo KPI SI en Excel.")
            book.close()
            # Reemplazo explícito permitido solo para el Excel generado,
            # jamás los RAW ni la SQLite histórica.
            temp_output.replace(output)
        except BaseException:
            try:
                book.close()
            except Exception:
                pass
            raise
        return {
            "status": "SIMULACION_COMPRAS_NO_VIGENCIAS",
            "activos_kpi_si": counters["activos_kpi_si"],
            "activos_sin_ventas": counters["activos_sin_ventas_identificadas"],
            "historicos_sin_activo": counters["historicos_no_en_activos"],
            "activos_excluidos_por_kpi": counters["activos_excluidos_kpi"],
            "meses_con_fuente": len(source.intersection(months)),
            "meses_sin_fuente": sorted(gaps),
            "niveles_activos": dict(levels_active),
            "niveles_historicos_provisionales": dict(levels_expired),
            "output": str(output),
        }
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--active-xlsx", required=True, type=Path)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    parser.add_argument("--replace", action="store_true",
                        help="Autoriza sustituir únicamente el Excel final previo.")
    parser.add_argument("--from-month", default=MONTH_START)
    parser.add_argument("--to-month", default=MONTH_END)
    args = parser.parse_args()
    result = generate(
        database=args.database, active_xlsx=args.active_xlsx, output=args.output,
        as_of=args.as_of, start_month=args.from_month, end_month=args.to_month,
        replace=args.replace,
    )
    import json
    print("[SUMMARY] " + json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
