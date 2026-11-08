"""Exporta una sola hoja de históricos NO presentes en Socios Activos.

Universo: IDs únicos de Venta Total hasta el 31-oct-2026 menos TODOS
los IDs del padrón Activos (incluso los KPI=No).
Métrica: MEJOR racha histórica estimada por cobertura de membresía.
La evidencia E significa inferida desde ventas, NO pago certificado.
El reporte Vencidos reciente es OPCIONAL y SOLO enriquece nombres cuando
PIN+sucursal enlazan un único ID; no limita el universo histórico.

PowerShell (desde backend):
  .\\.venv\\Scripts\\python.exe -m scripts.ops.export_expired_streak_oct_cutoff \\
    --active-xlsx "$HOME\\Downloads\\Reporte Socios Activos.xlsx" \\
    --expired-xlsx "$HOME\\Downloads\\Reporte Socios Vencidos.xlsx" \\
    --output "data\\backfill\\gasca_venta_total_enriched\\consolidated\\Vencidos_Mejor_Racha_2026-10-31.xlsx"
"""
from __future__ import annotations

import argparse
import itertools
import json
import sqlite3
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Iterator
from zipfile import ZipFile

from lxml import etree
import xlsxwriter

from scripts.ops.consolidate_gasca_member_sales import (
    XML_NS, _cell_text, _column_number, _shared_strings,
)
from scripts.ops.export_active_streak_oct_cutoff import (
    CUTOFF, MONTHS, MONTH_START, add_months, inferred_months, _merge_periods,
)
from scripts.ops.export_member_streaks_presentation import (
    _calendar_date, _norm_id, load_active,
)
from scripts.ops.profile_gasca_member_sales import DEFAULT_DATABASE


HEADERS = (
    "ID Socio", "Nombre", "PIN", "Sucursal ultima VT",
    "Ultimo producto VT", "Tarifa muestra Vencidos",
    "Ultimo pago muestra", "Vencimiento muestra",
    "Mejor racha historica (estimada)", "Inicio mejor racha",
    "Fin mejor racha", "Identidad nombre", "Evidencia",
)


def iter_expired_roster(path: Path) -> Iterator[dict[str, str]]:
    required = (
        "Pin", "Nombre", "Sucursal", "Tarifa",
        "Fecha Último Pago", "Fecha Vencimiento",
    )
    with ZipFile(path) as archive:
        shared = _shared_strings(archive)
        mapping: dict[str, int] = {}
        used: set[int] = set()
        with archive.open("xl/worksheets/sheet1.xml") as stream:
            for _, row in etree.iterparse(
                stream, events=("end",), tag=XML_NS + "row",
            ):
                cells = {
                    _column_number(cell.get("r", "")): _cell_text(cell, shared)
                    for cell in row.iterchildren(XML_NS + "c")
                    if not used or _column_number(cell.get("r", "")) in used
                }
                if not mapping:
                    headers = {value.strip(): col for col, value in cells.items()}
                    if all(field in headers for field in required):
                        mapping = {name: headers[name] for name in required}
                        used = set(mapping.values())
                    elif int(row.get("r") or "0") > 6:
                        raise ValueError("Encabezados de Vencidos no encontrados.")
                elif cells.get(mapping["Pin"], "").strip():
                    yield {
                        field: cells.get(col, "").strip()
                        for field, col in mapping.items()
                    }
                row.clear()
                while row.getprevious() is not None:
                    del row.getparent()[0]
        if not mapping:
            raise ValueError("No se encontraron encabezados del reporte Vencidos.")


def roster_enrichment(
    conn: sqlite3.Connection, expired_xlsx: Path | None,
    active_ids: set[str],
) -> tuple[dict[str, dict], Counter]:
    stats = Counter()
    if expired_xlsx is None:
        return {}, stats
    if not expired_xlsx.is_file():
        raise FileNotFoundError(f"No existe archivo Vencidos reciente: {expired_xlsx}")
    aliases: dict[tuple[str, str], str | None] = {}
    for mid, pin, branch in conn.execute("""
        SELECT DISTINCT id_socio, pin, sucursal FROM purchase_events
    """):
        alias = (str(branch or "").upper().strip(), str(pin or "").strip())
        if not all(alias):
            continue
        mid = _norm_id(mid)
        if alias not in aliases:
            aliases[alias] = mid
        elif aliases[alias] != mid:
            aliases[alias] = None  # PIN/sucursal no distingue un solo ID
    matched: dict[str, dict] = {}
    conflicting: set[str] = set()
    for row in iter_expired_roster(expired_xlsx):
        stats["filas_muestra"] += 1
        alias = (row["Sucursal"].upper().strip(), row["Pin"].strip())
        mid = aliases.get(alias)
        if mid is None:
            stats["sin_id_unico"] += 1
            continue
        if mid in active_ids:
            stats["coincidentes_con_activos_excluidos"] += 1
            continue
        candidate = {
            "nombre": row["Nombre"].strip(),
            "tarifa": row["Tarifa"],
            "pago": _calendar_date(row["Fecha Último Pago"]),
            "vence": _calendar_date(row["Fecha Vencimiento"]),
        }
        if not candidate["nombre"]:
            continue
        if mid in matched and matched[mid] != candidate:
            conflicting.add(mid)
        else:
            matched[mid] = candidate
    for mid in conflicting:
        matched.pop(mid, None)
    stats["nombres_enriquecidos"] = len(matched)
    stats["ids_muestra_ambiguos"] = len(conflicting)
    return matched, stats


def best_historical_streak(
    periods: list[tuple[date, date, str]],
    *, cutoff: date = CUTOFF,
) -> dict:
    """Selecciona el mayor bloque continuo, aunque haya terminado antes del corte."""
    cutoff_end = cutoff + timedelta(days=1)
    merged = _merge_periods([
        (max(start, MONTH_START), min(end, cutoff_end), source)
        for start, end, source in periods
        if start < cutoff_end and end > MONTH_START
    ])
    best = None
    best_months = 0
    for start, end, _ in merged:
        if end <= start:
            continue
        last = end - timedelta(days=1)
        months = (last.year - start.year) * 12 + last.month - start.month + 1
        if months > best_months or (
            months == best_months and best is not None and end > best[1]
        ):
            best, best_months = (start, end), months
    if best is None:
        return {
            "mejor": None, "inicio": "", "fin": "",
            "meses": set(), "calidad": "SIN_RACHA_INFERIBLE",
        }
    # Como en Activos, las E mensuales representan SOLO la racha
    # seleccionada, no todos los episodios históricos separados.
    covered = set()
    current = date(best[0].year, best[0].month, 1)
    while current < best[1]:
        if add_months(current, 1) > best[0]:
            token = f"{current.year:04d}-{current.month:02d}"
            if token in MONTHS:
                covered.add(token)
        current = add_months(current, 1)
    return {
        "mejor": best_months, "inicio": best[0].isoformat(),
        "fin": (best[1] - timedelta(days=1)).isoformat(),
        "meses": covered, "calidad": "SOLO_VENTAS_ESTIMADAS",
    }


def generate(*, database: Path, active_xlsx: Path, output: Path,
             expired_xlsx: Path | None = None, cutoff: date = CUTOFF) -> dict:
    if cutoff != CUTOFF:
        raise ValueError("Este muestreo está fijado al 2026-10-31.")
    sources = [database.resolve(), active_xlsx.resolve()]
    if expired_xlsx is not None:
        sources.append(expired_xlsx.resolve())
    if output.resolve() in sources:
        raise ValueError("El Excel no debe sobrescribir archivos fuente.")
    if output.exists():
        raise FileExistsError(f"El archivo ya existe: {output}. Utiliza otro nombre.")
    temp = output.with_name(output.stem + ".partial.xlsx")
    if temp.exists():
        raise FileExistsError(f"Existe una exportación parcial: {temp}.")
    if not database.is_file():
        raise FileNotFoundError(f"Falta histórico local: {database}")
    active, _ = load_active(active_xlsx)
    active_ids = set(active)
    conn = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        conn.execute("PRAGMA query_only = ON")
        if not conn.execute(
            "SELECT 1 FROM purchase_events WHERE source_month = ? LIMIT 1",
            (f"{cutoff:%Y-%m}",),
        ).fetchone():
            raise ValueError("Venta Total no tiene octubre 2026.")
        enrichment, enriched_counts = roster_enrichment(conn, expired_xlsx, active_ids)
        output.parent.mkdir(parents=True, exist_ok=True)
        wb = xlsxwriter.Workbook(str(temp), {
            "constant_memory": True, "strings_to_urls": False,
            "strings_to_formulas": False, "use_zip64": True,
        })
        fmt = {
            "title": wb.add_format({
                "bold": True, "bg_color": "#193A5B",
                "font_color": "#FFFFFF", "font_size": 15,
            }),
            "header": wb.add_format({
                "bold": True, "bg_color": "#27557C",
                "font_color": "#FFFFFF", "text_wrap": True,
            }),
            "sub": wb.add_format({"font_color": "#64748B"}),
            "integer": wb.add_format({"bold": True, "num_format": "#,##0"}),
            "estimated": wb.add_format({
                "align": "center", "bg_color": "#FFF3D6",
                "font_color": "#875F16",
            }),
        }
        sheet = wb.add_worksheet("Vencidos")
        sheet.hide_gridlines(2)
        sheet.set_zoom(85)
        sheet.merge_range(
            0, 0, 0, len(HEADERS)-1,
            "ULTRA GYM | VENCIDOS - MEJOR RACHA HISTORICA AL 31 OCT 2026",
            fmt["title"],
        )
        sheet.merge_range(
            1, 0, 1, len(HEADERS)-1,
            "Universo: ID Socio de Venta Total NO presente en Activos (incluye KPI=No excluidos). E = cobertura estimada desde Venta Total.",
            fmt["sub"],
        )
        sheet.merge_range(
            2, 0, 2, len(HEADERS)-1,
            "Nombre solo si PIN+sucursal coincide de manera unica con muestra reciente Vencidos. El historico no tiene nombres ni KPI.",
            fmt["sub"],
        )
        sheet.set_row(4, 34)
        sheet.write_row(4, 0, (*HEADERS, *MONTHS), fmt["header"])
        for col, width in enumerate(
            (16, 40, 16, 24, 40, 35, 17, 19, 26, 17, 17, 26, 27)
        ):
            sheet.set_column(col, col, width)
        sheet.set_column(len(HEADERS), len(HEADERS)+len(MONTHS)-1, 10)
        sheet.freeze_panes(5, 2)
        month_col = {m: len(HEADERS)+i for i, m in enumerate(MONTHS)}
        stats = Counter()
        rowno = 5
        try:
            cursor = conn.execute("""
                SELECT id_socio, pin, sucursal, fecha, tipo, descripcion,
                       estatus, total
                FROM purchase_events
                ORDER BY id_socio, fecha, folio
            """)
            for member_id, events in itertools.groupby(
                cursor, key=lambda x: _norm_id(x[0])
            ):
                if member_id in active_ids:
                    stats["ids_activos_excluidos"] += 1
                    continue
                last_pin = last_branch = last_product = ""
                intervals: list[tuple[date, date, str]] = []
                for _, pin, branch, raw_date, kind, description, status, total in events:
                    last_pin, last_branch = str(pin or ""), str(branch or "").upper()
                    last_product = str(description or "")
                    if str(status or "").upper() != "ACTIVO":
                        continue
                    try:
                        day = date.fromisoformat(str(raw_date))
                    except ValueError:
                        stats["fechas_invalidas"] += 1
                        continue
                    if day > cutoff or day < MONTH_START:
                        continue
                    n = inferred_months(kind, description)
                    if n is None or n < 1:
                        stats["tipos_sin_duracion"] += 1
                        continue
                    intervals.append((day, add_months(day, n), "VENTA_INFERIDA"))
                    stats["movimientos_inferidos"] += 1
                result = best_historical_streak(intervals, cutoff=cutoff)
                extra = enrichment.get(member_id, {})
                source_name = "MUESTRA_VENCIDOS" if extra else "NO_DISPONIBLE"
                values = (
                    member_id, extra.get("nombre", ""),
                    last_pin, last_branch, last_product,
                    extra.get("tarifa", ""), extra.get("pago", ""),
                    extra.get("vence", ""), result["mejor"],
                    result["inicio"], result["fin"], source_name, result["calidad"],
                )
                for col, value in enumerate(values):
                    if col == 8:
                        if value is not None:
                            sheet.write_number(rowno, col, value, fmt["integer"])
                    else:
                        sheet.write_string(rowno, col, str(value or ""))
                for month in sorted(result["meses"]):
                    sheet.write_string(rowno, month_col[month], "E", fmt["estimated"])
                stats["historicos_sin_activo"] += 1
                stats["con_mejor_racha" if result["mejor"] else "sin_racha_inferible"] += 1
                stats["nombre_enriquecido" if extra else "nombre_no_disponible"] += 1
                rowno += 1
            sheet.autofilter(
                4, 0, max(5, rowno-1),
                len(HEADERS)+len(MONTHS)-1,
            )
            wb.close()
            temp.replace(output)
        except BaseException:
            try:
                wb.close()
            except Exception:
                pass
            raise
        return {
            "estado": "MEJOR_RACHA_HISTORICA_ESTIMADA_2026-10-31",
            "universo": "VENTA_TOTAL_NO_ACTIVOS",
            "historicos_sin_activo": stats["historicos_sin_activo"],
            "con_mejor_racha": stats["con_mejor_racha"],
            "sin_racha_inferible": stats["sin_racha_inferible"],
            "nombres_recuperados": stats["nombre_enriquecido"],
            "nombres_no_disponibles": stats["nombre_no_disponible"],
            "activos_excluidos": stats["ids_activos_excluidos"],
            "movimientos_inferidos": stats["movimientos_inferidos"],
            "muestra_vencidos": dict(enriched_counts),
            "output": str(output),
            "advertencia": "E es cobertura historica estimada, no vigencia certificada; KPI historico no disponible.",
        }
    finally:
        conn.close()


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--active-xlsx", type=Path, required=True)
    cli.add_argument("--expired-xlsx", type=Path, default=None)
    cli.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    result = generate(
        database=args.database, active_xlsx=args.active_xlsx,
        expired_xlsx=args.expired_xlsx, output=args.output,
    )
    print("[RESUMEN_RACHA_VENCIDOS] " + json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
