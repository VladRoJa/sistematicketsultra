"""Diagnostico SOLO LECTURA de cobertura de fuentes para rachas en Warehouse.

Uso: cd backend && python -m scripts.ops.profile_member_streak_sources
     python -m scripts.ops.profile_member_streak_sources --output /tmp/fuentes_rachas.json

No descarga Gasca, no toca datos personales, ni cambia canonicalidad.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import text

from app import create_app
from app.extensions import db


SOURCES = (
    ("venta_total", "venta_total_snapshots", "business_date", True),
    ("socios_activos", "socios_activos_snapshots", "cutoff_date", True),
    ("socios_vencidos", "socios_vencidos_snapshots", "date_to", False),
    (
        "ventas_nuevos_socios_detalle",
        "ventas_nuevos_socios_detalle_snapshots",
        "date_to",
        True,
    ),
)


def _serializable(value: object) -> object:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _rows(query: str, params: dict | None = None) -> list[dict]:
    return [
        {key: _serializable(val) for key, val in row._mapping.items()}
        for row in db.session.execute(text(query), params or {})
    ]


def build_coverage_profile() -> dict:
    """Consulta exclusivamente metadatos de snapshots y muestra NO identificativa."""
    db.session.execute(text("SET TRANSACTION READ ONLY"))
    result: dict = {
        "warning": (
            "Fechas de snapshot NO equivalen a vigencias pagadas. "
            "Sin periodos de cobertura verificables no se certifican rachas."
        ),
        "sources": {},
    }
    for key, table, date_column, canonical in SOURCES:
        canonical_select = (
            "SUM(CASE WHEN is_canonical THEN 1 ELSE 0 END) AS canonical_snapshots,"
            if canonical
            else "NULL::bigint AS canonical_snapshots,"
        )
        totals = _rows(
            f"SELECT COUNT(*) AS snapshots, "
            f"MIN({date_column}) AS first_snapshot_date, "
            f"MAX({date_column}) AS last_snapshot_date, "
            f"COALESCE(SUM(row_count_valid),0) AS rows_reported, "
            f"{canonical_select} "
            f"COUNT(DISTINCT date_trunc('month', {date_column})) AS months_with_snapshots "
            f"FROM {table}"
        )[0]
        monthly = _rows(
            f"SELECT to_char({date_column}, 'YYYY-MM') AS month, "
            f"COUNT(*) AS snapshots, "
            f"COALESCE(SUM(row_count_valid),0) AS rows_reported "
            f"FROM {table} GROUP BY 1 ORDER BY 1"
        )
        result["sources"][key] = {"total": totals, "by_month": monthly}

    # Solo muestra del ultimo snapshot canonico: no extrapolar al historico.
    selected = _rows(
        "SELECT id, business_date FROM venta_total_snapshots "
        "WHERE is_canonical = true "
        "ORDER BY business_date DESC, captured_at DESC, id DESC LIMIT 1"
    )
    if selected:
        sample = _rows(
            "SELECT tipo, estatus, COUNT(*) AS sample_rows, "
            "COUNT(*) FILTER (WHERE pin IS NOT NULL AND btrim(pin) <> '') AS rows_with_pin "
            "FROM (SELECT tipo, estatus, pin FROM venta_total_snapshot_rows "
            "WHERE snapshot_id = :snapshot_id LIMIT 2000) t "
            "GROUP BY tipo, estatus ORDER BY sample_rows DESC LIMIT 30",
            {"snapshot_id": selected[0]["id"]},
        )
        result["venta_total_sample"] = {
            "snapshot_date": selected[0]["business_date"],
            "sample_max_rows": 2000,
            "by_type_status": sample,
            "note": "Muestra no representativa; no es un historial de vigencias.",
        }
    else:
        result["venta_total_sample"] = {"note": "No hay snapshot canonico."}
    result["source_gap"] = (
        "Ninguna de estas cuatro fuentes contiene en sus schemas "
        "inicio y fin de cada periodo pagado por socio. "
        "Se requiere un reporte adicional o resolver los contratos por folio."
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    app = create_app()
    with app.app_context():
        try:
            data = build_coverage_profile()
        finally:
            db.session.rollback()
            db.session.remove()
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
        print(f"Diagnostico escrito en {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
