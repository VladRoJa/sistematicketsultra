"""Simulador de una hoja: racha VIGENTE al 31-oct-2026 en Socios Activos.

Combina vigencia del padrón (último pago/vencimiento) con intervalos
*estimados* de Venta Total. NO certifica todos los pagos históricos ni
aplica descuentos. El padrón de noviembre solo define población, no
autoriza sumar días posteriores al corte de octubre.

Uso local desde backend:
  .\\.venv\\Scripts\\python.exe -m scripts.ops.export_active_streak_oct_cutoff \\
    --active-xlsx "$HOME\\Downloads\\Reporte Socios Activos.xlsx" \\
    --output "data\\backfill\\gasca_venta_total_enriched\\consolidated\\Activos_Racha_al_2026-10-31.xlsx"
"""
from __future__ import annotations

import argparse
import calendar
import json
import re
import sqlite3
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import xlsxwriter

from scripts.ops.export_member_streaks_presentation import (
    _norm_id, load_active,
)
from scripts.ops.profile_gasca_member_sales import DEFAULT_DATABASE


CUTOFF = date(2026, 10, 31)
MONTH_START = date(2020, 1, 1)
MONTHS = tuple(
    f"{year:04d}-{month:02d}"
    for year in range(2020, 2027)
    for month in range(1, 13)
    if (year, month) <= (2026, 10)
)
PERIOD_MONTHS = {
    "MENSUAL SIN CONTRATO": 1,
    "BIMESTRAL SIN CONTRATO": 2,
    "TRIMESTRAL SIN CONTRATO": 3,
    "SEMESTRAL SIN CONTRATO": 6,
    "ANUALIDAD SIN CONTRATO": 12,
    "CONTRATO": 1,
}
BASE_HEADERS = (
    "ID Socio", "Nombre", "PIN", "Sucursal", "Tarifa",
    "Ultimo pago padron", "Vencimiento padron",
    "Racha vigente al 31-oct (estimada)", "Inicio racha estimada",
    "Evidencia", "Meses estimados en cadena",
)


def add_months(day: date, count: int) -> date:
    if count < 1:
        raise ValueError("La duración debe ser positiva.")
    month_zero = day.month - 1 + count
    year = day.year + month_zero // 12
    month = month_zero % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def inferred_months(tipo: str, description: str) -> int | None:
    """No interpretar plazo CONTRATO '12 meses' como doce meses PAGADOS."""
    kind = (tipo or "").upper().strip()
    months = PERIOD_MONTHS.get(kind)
    if months is None:
        return None
    if kind == "CONTRATO":
        return 1
    # En prepagos, solo un texto no ambiguo N MESES; "3 MESES DE
    # REGALO" indica regalo adicional, NO duración total.
    title = (description or "").upper()
    if re.search(r"\\bREGALO\\b|\\bGRATIS\\b", title):
        return months
    durations = {
        int(m.group(1))
        for m in re.finditer(r"\\b(\\d{1,2})\\s+MESES?\\b", title)
        if 1 <= int(m.group(1)) <= 24
    }
    return next(iter(durations)) if len(durations) == 1 else months


def _merge_periods(periods: list[tuple[date, date, str]]) -> list[tuple[date, date, set[str]]]:
    merged: list[tuple[date, date, set[str]]] = []
    for start, end, origin in sorted(periods, key=lambda r: (r[0], r[1])):
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            prior_start, prior_end, sources = merged[-1]
            merged[-1] = prior_start, max(end, prior_end), sources | {origin}
        else:
            merged.append((start, end, {origin}))
    return merged


def active_streak(*, last_paid: str, expires: str,
                  historic: list[tuple[date, date, str]],
                  cutoff: date = CUTOFF) -> dict:
    """Una racha es el bloque sin cortes que CONTIENE el 31-oct-2026.

    La renovación del padrón se interpreta como fecha final inclusiva.
    Las compras de Venta Total estiman desde fecha de venta por modalidad;
    periodos futuros no cuentan y el estatus ACTIVO de Venta Total NO
    equivale a pago conciliado.
    """
    periods = list(historic)
    has_roster = False
    try:
        start = date.fromisoformat(last_paid)
        expiry = date.fromisoformat(expires)
    except (ValueError, TypeError):
        start = expiry = None
    if start is not None and expiry is not None and start <= cutoff <= expiry:
        has_roster = True
        periods.append((start, expiry + timedelta(days=1), "PADRON"))
    spans = _merge_periods(periods)
    chain = next(
        ((start, end, kinds) for start, end, kinds in spans
         if start <= cutoff < end), None
    )
    if chain is None:
        return {
            "racha": None, "desde": "", "evidencia": "SIN_COBERTURA_OBSERVABLE_AL_CORTE",
            "estimados": 0, "months": {},
        }
    start, end, sources = chain
    month_count = (cutoff.year - start.year) * 12 + cutoff.month - start.month + 1
    evidence = (
        "PADRON_Y_VENTAS_ESTIMADAS" if "PADRON" in sources and "VENTA_INFERIDA" in sources
        else "SOLO_PADRON" if "PADRON" in sources
        else "SOLO_VENTAS_ESTIMADAS"
    )
    flags = {}
    for year_month in MONTHS:
        month = date.fromisoformat(year_month + "-01")
        nxt = add_months(month, 1)
        if month < end and nxt > start and month <= cutoff:
            # V = intervalo del padrón; E = extendido por ventas estimadas
            flags[year_month] = "V" if has_roster and start >= date.fromisoformat(last_paid) and (
                month <= date.fromisoformat(expires) and nxt > date.fromisoformat(last_paid)
            ) else "E"
    return {
        "racha": month_count, "desde": start.isoformat(), "evidencia": evidence,
        "estimados": sum(flag == "E" for flag in flags.values()),
        "months": flags,
    }


def generate(*, database: Path, active_xlsx: Path, output: Path,
             cutoff: date = CUTOFF) -> dict:
    if cutoff != CUTOFF:
        raise ValueError("Este muestreo está fijado al 2026-10-31.")
    if output.resolve() in {database.resolve(), active_xlsx.resolve()}:
        raise ValueError("La salida no puede sobreescribir sus fuentes.")
    if output.exists():
        raise FileExistsError(f"Ya existe {output}. Usa un nombre nuevo.")
    temp = output.with_name(output.stem + ".partial.xlsx")
    if temp.exists():
        raise FileExistsError(f"Existe exportación parcial: {temp}.")
    if not database.is_file():
        raise FileNotFoundError(f"No existe SQLite histórica: {database}")
    people, counts = load_active(active_xlsx)
    eligible = {key: p for key, p in people.items() if p.kpi == "SI"}
    periods: dict[str, list[tuple[date, date, str]]] = {}
    source_counts = Counter()
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        conn.execute("PRAGMA query_only = ON")
        have_month = conn.execute(
            "SELECT COUNT(*) FROM purchase_events WHERE source_month = '2026-10'"
        ).fetchone()[0]
        if not have_month:
            raise ValueError("No existe el mes de referencia octubre 2026 en SQLite.")
        for mid, raw_date, kind, desc, status in conn.execute("""
            SELECT id_socio, fecha, tipo, descripcion, estatus
            FROM purchase_events
            ORDER BY id_socio, fecha
        """):
            mid = _norm_id(mid)
            if mid not in eligible or status != "ACTIVO":
                continue
            try:
                day = date.fromisoformat(str(raw_date))
            except ValueError:
                source_counts["fechas_invalidas"] += 1
                continue
            if day > cutoff:
                continue
            months = inferred_months(kind, desc)
            if months is None:
                source_counts["tipos_sin_duracion"] += 1
                continue
            if day < MONTH_START:
                continue
            periods.setdefault(mid, []).append(
                (day, add_months(day, months), "VENTA_INFERIDA")
            )
            source_counts["ventas_inferidas"] += 1
    output.parent.mkdir(parents=True, exist_ok=True)
    book = xlsxwriter.Workbook(str(temp), {
        "constant_memory": True, "strings_to_urls": False,
        "strings_to_formulas": False, "use_zip64": True,
    })
    styles = {
        "title": book.add_format({"bold": True, "font_size": 15, "bg_color": "#193A5B", "font_color": "#FFFFFF"}),
        "sub": book.add_format({"font_color": "#56657A"}),
        "header": book.add_format({"bold": True, "bg_color": "#27557C", "font_color": "#FFFFFF", "text_wrap": True}),
        "int": book.add_format({"num_format": "#,##0", "bold": True}),
        "verified": book.add_format({"bg_color": "#D9F2E2", "font_color": "#166534", "align": "center"}),
        "estimated": book.add_format({"bg_color": "#FFF3D6", "font_color": "#875F16", "align": "center"}),
        "note": book.add_format({"font_color": "#64748B"}),
    }
    sheet = book.add_worksheet("Activos")
    sheet.hide_gridlines(2)
    sheet.set_zoom(85)
    sheet.merge_range(0, 0, 0, len(BASE_HEADERS)-1, "ULTRA GYM  |  RACHA VIGENTE DE ACTIVOS AL 31 OCT 2026", styles["title"])
    sheet.merge_range(1, 0, 1, len(BASE_HEADERS)-1,
        "Solo Aplica KPI=SI. V = vigencia según padrón; E = periodo inferido desde Venta Total. No son pagos bancarios conciliados.",
        styles["sub"])
    sheet.merge_range(2, 0, 2, len(BASE_HEADERS)-1,
        "La racha termina exactamente en octubre; meses de noviembre en adelante NO cuentan. Sin datos = pendiente, no cero certificado.",
        styles["sub"])
    sheet.set_row(4, 35)
    sheet.write_row(4, 0, (*BASE_HEADERS, *MONTHS), styles["header"])
    for col, width in enumerate([16, 38, 16, 24, 40, 18, 18, 23, 18, 32, 22]):
        sheet.set_column(col, col, width)
    sheet.set_column(len(BASE_HEADERS), len(BASE_HEADERS) + len(MONTHS)-1, 10)
    sheet.freeze_panes(5, 2)
    stats = Counter()
    row_index = 5
    try:
        for mid, person in sorted(eligible.items()):
            result = active_streak(
                last_paid=person.last_payment, expires=person.expires,
                historic=periods.get(mid, []), cutoff=cutoff,
            )
            racha = result["racha"]
            row = [
                mid, person.name, person.pin, person.branch, person.tarifa,
                person.last_payment, person.expires, racha,
                result["desde"], result["evidencia"], result["estimados"],
            ]
            for col, value in enumerate(row):
                if col in (7, 10) and value is not None:
                    sheet.write_number(row_index, col, value, styles["int"])
                elif value is not None:
                    sheet.write_string(row_index, col, str(value))
            for month, flag in result["months"].items():
                col = len(BASE_HEADERS) + MONTHS.index(month)
                sheet.write_string(row_index, col, flag,
                                   styles["verified"] if flag == "V" else styles["estimated"])
            stats[result["evidencia"]] += 1
            row_index += 1
        sheet.autofilter(4, 0, row_index-1, len(BASE_HEADERS)+len(MONTHS)-1)
        book.close()
        temp.replace(output)
    except Exception:
        try:
            book.close()
        except Exception:
            pass
        raise
    return {
        "estado": "RACHA_VIGENTE_SIMULADA_AL_2026-10-31",
        "activos_kpi_si": counts["activos_kpi_si"],
        "activos_procesados": row_index-5,
        "evidencia": dict(stats), "ventas_inferidas": source_counts["ventas_inferidas"],
        "output": str(output),
        "nota": "Estimaciones de Venta Total; sin pagos históricos certificados",
    }


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--active-xlsx", type=Path, required=True)
    cli.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    result = generate(database=args.database, active_xlsx=args.active_xlsx, output=args.output)
    print("[RESUMEN_RACHA_ACTIVOS] " + json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
