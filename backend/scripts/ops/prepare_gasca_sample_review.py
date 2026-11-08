"""Prepara una revisión manual en Gasca de los casos muestra de rachas.

Salida XLSX LOCAL confidencial, sin validar automáticamente pagos ni vigencias.
Lee SQLite consolidada en modo RO y el Excel original de Socios Activos.
Ejemplo (PowerShell en backend):
.\\.venv\\Scripts\\python.exe -m scripts.ops.prepare_gasca_sample_review --active-xlsx "$HOME\\Downloads\\Reporte Socios Activos.xlsx" --as-of 2026-11-07 --output "data\\backfill\\gasca_venta_total_enriched\\consolidated\\Revision_12_Casos_Gasca.xlsx"
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from contextlib import closing
from datetime import date
from pathlib import Path

import xlsxwriter

from scripts.ops.audit_active_streak_gaps import audit
from scripts.ops.profile_gasca_member_sales import DEFAULT_DATABASE


REVIEW_STATUS = ("PENDIENTE", "CONFIRMADO", "INCONSISTENTE", "SIN_EVIDENCIA")
PAYMENT_STATUS = ("PENDIENTE", "COBRO_CONFIRMADO", "NO_COBRADO", "NO_APLICA")


def collect(*, database: Path, active_xlsx: Path, as_of: date,
            sales_cutoff: str) -> tuple[list[dict], list[dict], dict]:
    summary, all_rows = audit(
        database=database, active_xlsx=active_xlsx, as_of=as_of,
        sales_cutoff=sales_cutoff,
    )
    sample = all_rows[-1]["__samples__"]
    identifiers = [str(row["id_socio"]) for row in sample]
    names_by_id = {str(row["id_socio"]): str(row["nombre"]) for row in sample}
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("La muestra contiene ID Socio duplicados.")
    movements: list[dict] = []
    if identifiers:
        placeholders = ",".join("?" for _ in identifiers)
        sql = f"""
            SELECT id_socio, pin, sucursal, source_month, fecha, folio,
                   tipo, descripcion, estatus, total
            FROM purchase_events WHERE id_socio IN ({placeholders})
            ORDER BY id_socio, fecha, folio
        """
        with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            conn.execute("PRAGMA query_only=ON")
            for mid, pin, branch, month, when, folio, kind, desc, status, total in conn.execute(
                sql, identifiers,
            ):
                movements.append({
                    "id_socio": str(mid),
                    "nombre": names_by_id[str(mid)],
                    "pin": str(pin),
                    "sucursal": str(branch),
                    "mes_venta": str(month),
                    "fecha_venta": str(when),
                    "folio": str(folio),
                    "tipo": str(kind),
                    "descripcion": str(desc),
                    "estatus": str(status),
                    "total": str(total),
                })
    meta = {
        "calidad": "MUESTRA_PENDIENTE_REVISION_GASCA",
        "casos": len(sample),
        "movimientos_de_muestra": len(movements),
        "casos_sin_movimientos": sum(
            1 for row in sample if row["movimientos"] == 0
        ),
        "tipos_ultima_compra": dict(Counter(
            row["tipo_ultima_compra"] or "SIN VENTA ACTIVA"
            for row in sample
        )),
        "corte_padron": as_of.isoformat(),
        "corte_venta_total": sales_cutoff,
    }
    return sample, movements, meta


def write_review(*, output: Path, sample: list[dict],
                 movements: list[dict], meta: dict, replace: bool = False) -> None:
    if output.exists() and not replace:
        raise FileExistsError(f"Ya existe {output}; usa otro nombre o --replace.")
    partial = output.with_name(output.stem + ".partial.xlsx")
    if partial.exists():
        raise FileExistsError(f"Existe exportación parcial: {partial}. Revisarla primero.")
    output.parent.mkdir(parents=True, exist_ok=True)
    wb = xlsxwriter.Workbook(
        str(partial), {"strings_to_formulas": False, "strings_to_urls": False},
    )
    try:
        title = wb.add_format({
            "bold": True, "bg_color": "#193A5B", "font_color": "#FFFFFF",
            "font_size": 15, "valign": "vcenter",
        })
        hdr = wb.add_format({
            "bold": True, "font_color": "white", "bg_color": "#27557C",
            "text_wrap": True, "valign": "vcenter",
        })
        input_hdr = wb.add_format({
            "bold": True, "font_color": "#663A00", "bg_color": "#FFE7B5",
            "text_wrap": True, "valign": "vcenter",
        })
        desc = wb.add_format({"font_color": "#5C6B7A"})
        pending = wb.add_format({"bg_color": "#FFF7E5", "font_color": "#946200"})
        amount = wb.add_format({"num_format": "#,##0"})
        cases = wb.add_worksheet("Casos a revisar")
        cases.hide_gridlines(2)
        cases.set_zoom(85)
        cases.set_row(0, 32)
        cases.merge_range("A1:Q1", "ULTRA GYM  |  Validación de casos contra Gasca", title)
        cases.merge_range(
            "A2:Q2", "Revisar cobro y vigencia en Gasca. Las fechas del padrón y las ventas NO certifican pago.", desc,
        )
        case_cols = [
            ("ID Socio", "id_socio", 17), ("Nombre", "nombre", 36),
            ("PIN", "pin", 17),
            ("Sucursal", "sucursal", 23), ("Tarifa padrón", "tarifa", 35),
            ("Último pago padrón", "fecha_ultimo_pago", 19),
            ("Vencimiento padrón", "fecha_vencimiento", 19),
            ("Tipo última venta", "tipo_ultima_compra", 26),
            ("Última venta", "ultima_compra_fecha", 17),
            ("Folio última venta", "folio_ultima_compra", 22),
            ("Movimientos", "movimientos", 13),
            ("Grupo", "grupo", 28),
            ("Vencimiento declarado", "estado_vencimiento", 31),
        ]
        for col, (heading, _, width) in enumerate(case_cols):
            cases.set_column(col, col, width)
            cases.write_string(3, col, heading, hdr)
        review_cols = [
            ("Revisión Gasca", 23),
            ("Cobro / servicio verificado", 26),
            ("Referencia verificación", 27),
            ("Observación", 48),
        ]
        for j, (heading, width) in enumerate(review_cols, len(case_cols)):
            cases.set_column(j, j, width)
            cases.write_string(3, j, heading, input_hdr)
        for i, r in enumerate(sample, 4):
            for j, (_, key, _) in enumerate(case_cols):
                value = r.get(key, "")
                if key == "movimientos":
                    cases.write_number(i, j, int(value or 0), amount)
                else:
                    cases.write_string(i, j, str(value or ""))
            cases.write_string(i, len(case_cols), "PENDIENTE", pending)
            cases.write_string(i, len(case_cols)+1, "POR_COMPROBAR", pending)
        cases.freeze_panes(4, 3)
        cases.autofilter(3, 0, max(4, len(sample)+3), len(case_cols)+len(review_cols)-1)
        if sample:
            cases.data_validation(4, len(case_cols), len(sample)+3, len(case_cols), {
                "validate": "list", "source": list(REVIEW_STATUS),
            })

        events = wb.add_worksheet("Movimientos y cobros")
        events.hide_gridlines(2)
        events.set_zoom(85)
        events.set_row(0, 31)
        events.merge_range(
            "A1:P1", "ULTRA GYM  |  Folios de Venta Total para la muestra", title,
        )
        events.merge_range(
            "A2:P2", "Una venta ACTIVO es solo un movimiento. Confirmar pago y periodo cubierto en Gasca antes de clasificar meses.", desc,
        )
        evt_cols = [
            ("ID Socio", "id_socio", 17), ("Nombre", "nombre", 36),
            ("PIN", "pin", 16),
            ("Sucursal venta", "sucursal", 22), ("Mes venta", "mes_venta", 13),
            ("Fecha venta", "fecha_venta", 16), ("Folio", "folio", 22),
            ("Tipo", "tipo", 28), ("Producto / descripción", "descripcion", 48),
            ("Estatus Venta Total", "estatus", 20), ("Importe VT", "total", 16),
        ]
        for j, (heading, _, width) in enumerate(evt_cols):
            events.set_column(j, j, width)
            events.write_string(3, j, heading, hdr)
        for j, (heading, width) in enumerate([
            ("Cobro validado", 25), ("Cobertura desde (AAAA-MM-DD)", 24),
            ("Cobertura hasta (AAAA-MM-DD)", 24),
            ("Referencia cobro Gasca", 25), ("Observación", 40),
        ], start=len(evt_cols)):
            events.set_column(j, j, width)
            events.write_string(3, j, heading, input_hdr)
        for i, r in enumerate(movements, 4):
            for j, (_, key, _) in enumerate(evt_cols):
                events.write_string(i, j, r[key])
            events.write_string(i, len(evt_cols), "PENDIENTE", pending)
        events.freeze_panes(4, 3)
        events.autofilter(3, 0, max(4, len(movements)+3), len(evt_cols)+4)
        if movements:
            events.data_validation(4, len(evt_cols), len(movements)+3, len(evt_cols), {
                "validate": "list", "source": list(PAYMENT_STATUS),
            })
        events.conditional_format(4, len(evt_cols), max(4, len(movements)+3), len(evt_cols), {
            "type": "text", "criteria": "containing",
            "value": "COBRO_CONFIRMADO", "format": wb.add_format({
                "bg_color": "#D9F2E2", "font_color": "#166534",
            }),
        })
        wb.close()
        partial.replace(output)
    except Exception:
        try:
            wb.close()
        except Exception:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--active-xlsx", type=Path, required=True)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    parser.add_argument("--sales-cutoff", default="2026-10")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    if args.output.resolve() in {args.database.resolve(), args.active_xlsx.resolve()}:
        raise ValueError("La salida no puede reemplazar el padrón ni la SQLite.")
    cases, events, summary = collect(
        database=args.database, active_xlsx=args.active_xlsx,
        as_of=args.as_of, sales_cutoff=args.sales_cutoff,
    )
    write_review(
        output=args.output, sample=cases, movements=events,
        meta=summary, replace=args.replace,
    )
    print("[MUESTRA_GASCA] " + json.dumps(summary, ensure_ascii=False))
    print("[OUTPUT] " + str(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
