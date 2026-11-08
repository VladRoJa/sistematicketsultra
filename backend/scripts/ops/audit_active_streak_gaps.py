"""Audita activos KPI=SI sin compra observada en el último mes de Venta Total.

No infiere pagos ni vigencias. Usa el propio padrón de Activos de Gasca
y la SQLite histórica LOCAL en modo lectura. El XLSX generado es PRIVADO.

PowerShell desde backend:
.\\.venv\\Scripts\\python.exe -m scripts.ops.audit_active_streak_gaps \\
  --active-xlsx "$HOME\\Downloads\\Reporte Socios Activos.xlsx" \\
  --as-of 2026-11-07 --sales-cutoff 2026-10 \\
  --output "data\\backfill\\gasca_venta_total_enriched\\consolidated\\Auditoria_Activos_Sin_Compra_Oct2026.xlsx"
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from datetime import date
from pathlib import Path

import xlsxwriter

from scripts.ops.export_member_streaks_presentation import (
    ActiveRow, _month_number, load_active,
)
from scripts.ops.profile_gasca_member_sales import DEFAULT_DATABASE


GROUPS = (
    ("SIN_HISTORIAL", "No aparece en Venta Total"),
    ("PAGO_PADRON_MES_POSTERIOR", "Último pago en el padrón, posterior al mes de ventas"),
    ("PAGO_PADRON_MES_CORTE", "Último pago en el mismo mes de corte"),
    ("PAGO_PADRON_MES_ANTERIOR", "Último pago anterior al mes de corte"),
    ("FECHA_PAGO_NO_DISPONIBLE", "Sin fecha de último pago interpretable"),
)


def _group(person: ActiveRow, *, cutoff: str, has_sale: bool) -> str:
    if not has_sale:
        return "SIN_HISTORIAL"
    pay_month = (person.last_payment or "")[:7]
    if not pay_month:
        return "FECHA_PAGO_NO_DISPONIBLE"
    if pay_month > cutoff:
        return "PAGO_PADRON_MES_POSTERIOR"
    if pay_month == cutoff:
        return "PAGO_PADRON_MES_CORTE"
    return "PAGO_PADRON_MES_ANTERIOR"


def audit(*, database: Path, active_xlsx: Path, sales_cutoff: str,
          as_of: date) -> tuple[dict, list[dict]]:
    _month_number(sales_cutoff)
    if sales_cutoff > f"{as_of:%Y-%m}":
        raise ValueError("No se permite mes de venta posterior a la fecha del padrón.")
    active, counts = load_active(active_xlsx)
    eligible = {mid: person for mid, person in active.items() if person.kpi == "SI"}
    if not database.is_file():
        raise FileNotFoundError(f"SQLite histórica no existe: {database}")

    # Estado mínimo en memoria: solo socios Activos KPI=SI, nunca PII en logs.
    signals = {mid: {
        "movimientos": 0, "oct_active": False, "last": None,
    } for mid in eligible}
    conn = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        conn.execute("PRAGMA query_only = ON")
        observed_source = {
            str(row[0]) for row in conn.execute(
                "SELECT DISTINCT source_month FROM purchase_events"
            )
        }
        if sales_cutoff not in observed_source:
            raise ValueError("No existe fuente validada para el último mes solicitado.")
        for mid, month, fecha, kind, status, folio, description in conn.execute("""
            SELECT id_socio, source_month, fecha, tipo, estatus, folio, descripcion
            FROM purchase_events
            ORDER BY id_socio, source_month, fecha
        """):
            signal = signals.get(str(mid).strip())
            if signal is None:
                continue
            signal["movimientos"] += 1
            if status != "ACTIVO" or month > sales_cutoff:
                continue
            if month == sales_cutoff:
                signal["oct_active"] = True
            # El cursor está ordenado cronológicamente ascendente.
            signal["last"] = (month, fecha, kind, folio, description)

        rows: list[dict] = []
        categories = Counter()
        tariffs = Counter()
        kinds = Counter()
        expirations = Counter()
        for mid, person in eligible.items():
            signal = signals[mid]
            if signal["oct_active"]:
                continue
            last = signal["last"]
            group = _group(person, cutoff=sales_cutoff,
                           has_sale=bool(signal["movimientos"]))
            categories[group] += 1
            tariff = person.tarifa.upper().strip() or "SIN TARIFA"
            tariffs[tariff] += 1
            kinds[(last[2] if last else "SIN VENTA ACTIVA")] += 1
            exp = person.expires
            if not exp:
                expire_status = "SIN_VENCIMIENTO"
            elif exp >= as_of.isoformat():
                expire_status = "VIGENTE_SEGUN_PADRON"
            else:
                expire_status = "VENCIMIENTO_ANTERIOR_AL_CORTE"
            expirations[expire_status] += 1
            rows.append({
                "id_socio": mid, "pin": person.pin, "sucursal": person.branch,
                "tarifa": person.tarifa, "fecha_ultimo_pago": person.last_payment,
                "fecha_vencimiento": person.expires,
                "ultima_compra_mes": last[0] if last else "",
                "ultima_compra_fecha": last[1] if last else "",
                "tipo_ultima_compra": last[2] if last else "",
                "folio_ultima_compra": last[3] if last else "",
                "descripcion_ultima_compra": last[4] if last else "",
                "movimientos": signal["movimientos"],
                "grupo": group, "estado_vencimiento": expire_status,
            })

        # Para investigar primero: cuatro casos por categoría y alternando
        # tipos de último movimiento; no selecciona aleatoriamente ni
        # acredita un pago por pertenecer a alguna categoría.
        samples: list[dict] = []
        for group, _ in GROUPS:
            selected = set()
            first_by_kind = {}
            group_rows = (r for r in rows if r["grupo"] == group)
            for r in group_rows:
                first_by_kind.setdefault(r["tipo_ultima_compra"], r)
            for r in first_by_kind.values():
                samples.append(r)
                selected.add(r["id_socio"])
                if sum(x["grupo"] == group for x in samples) == 4:
                    break
            if sum(x["grupo"] == group for x in samples) < 4:
                for r in rows:
                    if r["grupo"] == group and r["id_socio"] not in selected:
                        samples.append(r)
                        selected.add(r["id_socio"])
                        if sum(x["grupo"] == group for x in samples) == 4:
                            break

        summary = {
            "calidad": "DIAGNOSTICO_COMPRAS_NO_VIGENCIAS",
            "padrón_fecha": as_of.isoformat(),
            "venta_total_hasta": sales_cutoff,
            "activos_kpi_si": counts["activos_kpi_si"],
            "activos_sin_compra_mes_corte": len(rows),
            "activos_sin_ventas_historicas": categories["SIN_HISTORIAL"],
            "por_grupo_ultimo_pago_padron": dict(categories),
            "por_tipo_ultima_compra": dict(kinds.most_common()),
            "estado_vencimiento_en_padron": dict(expirations),
            "por_tarifa_padron": dict(tariffs.most_common(20)),
            "muestra_casos_para_gasca": len(samples),
        }
        return summary, [*rows, {"__samples__": samples}]
    finally:
        conn.close()


def write_excel(*, output: Path, summary: dict, rows_and_sample: list[dict],
                replace: bool = False) -> None:
    if output.exists() and not replace:
        raise FileExistsError(f"Ya existe: {output}. Usa --replace si deseas sustituirlo.")
    partial = output.with_name(output.stem + ".partial.xlsx")
    if partial.exists():
        raise FileExistsError(f"Existe exportación parcial: {partial}. Revisar antes.")
    rows = rows_and_sample[:-1]
    sample = rows_and_sample[-1]["__samples__"]
    output.parent.mkdir(parents=True, exist_ok=True)
    book = xlsxwriter.Workbook(str(partial), {
        "constant_memory": True, "strings_to_urls": False,
    })
    try:
        fmt = {
            "title": book.add_format({"bold": True, "font_size": 17,
                                      "bg_color": "#193A5B", "font_color": "white"}),
            "header": book.add_format({"bold": True, "bg_color": "#27557C",
                                       "font_color": "white", "text_wrap": True}),
            "integer": book.add_format({"num_format": "#,##0"}),
            "sub": book.add_format({"font_color": "#5C6B7A"}),
            "warning": book.add_format({"bg_color": "#FFF3D6", "font_color": "#815C18"}),
        }
        main = book.add_worksheet("Resumen")
        main.hide_gridlines(2)
        main.set_column("A:A", 43)
        main.set_column("B:B", 22)
        main.set_column("D:D", 43)
        main.set_column("E:E", 17)
        main.merge_range("A1:F1", "ULTRA GYM  |  Por qué 4,109 activos no muestran compra en octubre", fmt["title"])
        main.merge_range("A2:F2",
                         "Análisis exploratorio de compras y fechas del padrón; NO constancia de meses pagados.",
                         fmt["sub"])
        main.write("A4", "Activos con Aplica KPI = Sí", fmt["header"])
        main.write_number("B4", summary["activos_kpi_si"], fmt["integer"])
        main.write("A5", "Sin compra en el mes de corte", fmt["header"])
        main.write_number("B5", summary["activos_sin_compra_mes_corte"], fmt["integer"])
        main.write("A6", "Sin ventas históricas identificadas", fmt["header"])
        main.write_number("B6", summary["activos_sin_ventas_historicas"], fmt["integer"])
        main.write("A8", "Fecha último pago según padrón", fmt["header"])
        main.write("B8", "Socios", fmt["header"])
        for idx, (group, desc) in enumerate(GROUPS, start=8):
            main.write_string(idx, 0, desc)
            main.write_number(idx, 1, summary["por_grupo_ultimo_pago_padron"].get(group, 0),
                              fmt["integer"])
        main.write("D8", "Vencimiento según padrón", fmt["header"])
        main.write("E8", "Socios", fmt["header"])
        for idx, (status, number) in enumerate(
                summary["estado_vencimiento_en_padron"].items(), start=8):
            main.write_string(idx, 3, status)
            main.write_number(idx, 4, number, fmt["integer"])
        main.write("A16", "Tipo de la última compra identificada", fmt["header"])
        main.write("B16", "Socios", fmt["header"])
        for idx, (kind, number) in enumerate(
                summary["por_tipo_ultima_compra"].items(), start=16):
            main.write_string(idx, 0, kind)
            main.write_number(idx, 1, number, fmt["integer"])
        main.merge_range("A30:F30",
                         "Los casos no se reclasifican como vencidos; deben cotejarse con Gasca.",
                         fmt["warning"])
        main.merge_range("A31:F31",
                         "Una anualidad puede cubrir meses sin compras repetidas; el padrón no prueba el cobro liquidado.",
                         fmt["sub"])
        main.merge_range("A32:F32",
                         "Archivos de diagnóstico con datos de socios: acceso privado; no enviar a GitHub.",
                         fmt["sub"])

        columns = [
            ("ID Socio", "id_socio", 17), ("PIN", "pin", 16),
            ("Sucursal", "sucursal", 24), ("Tarifa actual", "tarifa", 33),
            ("Fecha último pago (padrón)", "fecha_ultimo_pago", 19),
            ("Vencimiento (padrón)", "fecha_vencimiento", 19),
            ("Última compra VT mes", "ultima_compra_mes", 18),
            ("Última compra VT fecha", "ultima_compra_fecha", 18),
            ("Tipo última compra", "tipo_ultima_compra", 25),
            ("Folio última compra", "folio_ultima_compra", 23),
            ("Descripción última compra", "descripcion_ultima_compra", 40),
            ("Movimientos históricos", "movimientos", 17),
            ("Grupo de revisión", "grupo", 31),
            ("Vencimiento declarado", "estado_vencimiento", 32),
        ]
        for sheet_name, records in (("Casos", rows), ("Muestra 20", sample)):
            ws = book.add_worksheet(sheet_name)
            ws.hide_gridlines(2)
            ws.set_zoom(85)
            ws.freeze_panes(1, 3)
            ws.set_row(0, 32)
            for col, (title, key, width) in enumerate(columns):
                ws.set_column(col, col, width)
                ws.write_string(0, col, title, fmt["header"])
            for i, record in enumerate(records, start=1):
                for col, (_, key, _) in enumerate(columns):
                    value = record.get(key, "")
                    if key == "movimientos":
                        ws.write_number(i, col, value, fmt["integer"])
                    else:
                        # No convertir ID/PIN/folio en número o fórmula.
                        ws.write_string(i, col, str(value or ""))
            ws.autofilter(0, 0, max(1, len(records)), len(columns)-1)
        book.close()
        partial.replace(output)
    except Exception:
        try:
            book.close()
        except Exception:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--active-xlsx", type=Path, required=True)
    parser.add_argument("--sales-cutoff", default="2026-10")
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    if args.output.resolve() in {args.database.resolve(), args.active_xlsx.resolve()}:
        raise ValueError("La salida no puede sobrescribir los archivos fuente.")
    summary, rows = audit(
        database=args.database, active_xlsx=args.active_xlsx,
        sales_cutoff=args.sales_cutoff, as_of=args.as_of,
    )
    write_excel(output=args.output, summary=summary, rows_and_sample=rows,
                replace=args.replace)
    print("[RESUMEN_VALIDACION] " + json.dumps(summary, ensure_ascii=False))
    print("[OUTPUT] " + str(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
