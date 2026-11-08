"""Diagnóstico SOLO LECTURA de continuidad de meses de COMPRA, no de cobertura.

Procesa por IDSocio, sin sacar PIN/IDs/folios al resultado. Una compra
al mes siguiente es indicio de renovación, NO comprobante de vigencia.

Windows PowerShell desde backend:
  .\\.venv\\Scripts\\python.exe -m scripts.ops.audit_gasca_purchase_cadence
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Iterator

from scripts.ops.profile_gasca_member_sales import DEFAULT_DATABASE


def _month_key(value: str) -> int:
    if len(value) != 7 or value[4] != "-" or not value[:4].isdigit() or not value[5:].isdigit():
        raise ValueError("Mes de origen inválido en SQLite.")
    year, month = int(value[:4]), int(value[5:])
    if not 1 <= month <= 12:
        raise ValueError("Mes fuera de rango.")
    return year * 12 + month - 1


def _member_groups(rows: Iterator[tuple[str, str, str, str]]):
    current = None
    types_by_month: dict[int, set[str]] = {}
    for member, source_month, kind, status in rows:
        if current != member:
            if current is not None:
                yield types_by_month
            current = member
            types_by_month = {}
        if status == "ACTIVO":
            types_by_month.setdefault(_month_key(source_month), set()).add(kind)
    if current is not None:
        yield types_by_month


def audit(database: Path) -> dict:
    if not database.is_file():
        raise FileNotFoundError(f"Consolidado SQLite inexistente: {database}")
    conn = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        conn.execute("PRAGMA query_only = ON")
        available = {
            _month_key(row[0])
            for row in conn.execute("SELECT DISTINCT source_month FROM purchase_events")
        }
        aggregates = defaultdict(lambda: {
            "socio_meses_con_compra_activa": 0,
            "socio_meses_comparables": 0,
            "con_cualquier_compra_al_mes_siguiente": 0,
            "con_compra_del_mismo_tipo_al_mes_siguiente": 0,
            "sin_compra_al_mes_siguiente": 0,
            "sin_mes_siguiente_verificado": 0,
        })
        rows = conn.execute("""
            SELECT id_socio, source_month, tipo, estatus
            FROM purchase_events
            ORDER BY id_socio, source_month
        """)
        for types_by_month in _member_groups(iter(rows)):
            for month, kinds in types_by_month.items():
                next_month = month + 1
                next_kinds = types_by_month.get(next_month, set())
                for kind in kinds:
                    stat = aggregates[kind]
                    stat["socio_meses_con_compra_activa"] += 1
                    if next_month not in available:
                        # No confundir un hueco de fuente o el final del corte
                        # con un socio que interrumpió pagos.
                        stat["sin_mes_siguiente_verificado"] += 1
                        continue
                    stat["socio_meses_comparables"] += 1
                    if next_kinds:
                        stat["con_cualquier_compra_al_mes_siguiente"] += 1
                    else:
                        stat["sin_compra_al_mes_siguiente"] += 1
                    if kind in next_kinds:
                        stat["con_compra_del_mismo_tipo_al_mes_siguiente"] += 1
        return {
            "advertencia": (
                "Solo mide meses de compras ACTIVO observados. "
                "No verifica cobros liquidados, ni duración o continuidad de servicio. "
                "Una anualidad pagada por adelantado puede no reaparecer al mes siguiente."
            ),
            "meses_con_fuente": len(available),
            "por_tipo": [
                {"tipo": kind, **stats}
                for kind, stats in sorted(
                    aggregates.items(),
                    key=lambda item: (-item[1]["socio_meses_con_compra_activa"], item[0]),
                )
            ],
        }
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    data = audit(args.database)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"[OUTPUT] {args.output}")
    print("[CADENCIA_COMPRA] " + json.dumps(data, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
