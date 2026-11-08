"""Perfil agregado y SOLO LECTURA de movimientos históricos de membresía.

No muestra IDs, PIN, folios ni descripciones individuales, no interpreta
ventas como vigencias pagadas y no modifica la base SQLite local.

PowerShell desde backend:
.\\.venv\\Scripts\\python.exe -m scripts.ops.profile_gasca_member_sales
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

DEFAULT_DATABASE = Path(
    "data/backfill/gasca_venta_total_enriched/consolidated/"
    "member_sales_202001_202610.sqlite"
)


def _query(conn: sqlite3.Connection, sql: str) -> list[dict]:
    cursor = conn.execute(sql)
    return [dict(zip((c[0] for c in cursor.description), row))
            for row in cursor.fetchall()]


def profile(database: Path) -> dict:
    if not database.is_file():
        raise FileNotFoundError(f"Consolidado SQLite inexistente: {database}")
    uri = database.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        conn.execute("PRAGMA query_only = ON")
        totals = _query(conn, """
            SELECT COUNT(*) AS movimientos,
                   COUNT(DISTINCT id_socio) AS ids_socios_distintos,
                   COUNT(DISTINCT source_month) AS meses_con_movimientos,
                   SUM(CASE WHEN estatus = 'ACTIVO' THEN 1 ELSE 0 END)
                       AS movimientos_estatus_activo
            FROM purchase_events
        """)[0]

        by_type_status = _query(conn, """
            SELECT tipo, estatus, COUNT(*) AS movimientos
            FROM purchase_events
            GROUP BY tipo, estatus
            ORDER BY movimientos DESC, tipo, estatus
        """)

        # Estas categorías son señales NO excluyentes. Se usan para identificar
        # reglas de negocio pendientes, nunca para asignar meses pagados.
        period_signals = _query(conn, """
            SELECT
               SUM(CASE WHEN tipo LIKE '%ANUAL%' OR descripcion LIKE '%12 MESES%'
                            OR UPPER(descripcion) LIKE '%ANUAL%'
                        THEN 1 ELSE 0 END) AS anual_o_12_meses,
               SUM(CASE WHEN tipo LIKE '%SEMESTRAL%'
                            OR UPPER(descripcion) LIKE '%SEMESTR%'
                            OR UPPER(descripcion) LIKE '%6 MESES%'
                        THEN 1 ELSE 0 END) AS semestral_o_6_meses,
               SUM(CASE WHEN tipo LIKE '%TRIMESTRAL%'
                            OR UPPER(descripcion) LIKE '%TRIMESTR%'
                            OR UPPER(descripcion) LIKE '%3 MESES%'
                        THEN 1 ELSE 0 END) AS trimestral_o_3_meses,
               SUM(CASE WHEN tipo LIKE '%BIMESTRAL%'
                            OR UPPER(descripcion) LIKE '%BIMESTR%'
                            OR UPPER(descripcion) LIKE '%2 MESES%'
                        THEN 1 ELSE 0 END) AS bimestral_o_2_meses,
               SUM(CASE WHEN UPPER(descripcion) LIKE '%DOMICILIAD%'
                        THEN 1 ELSE 0 END) AS domiciliado,
               SUM(CASE WHEN UPPER(descripcion) LIKE '%RECURREN%'
                        THEN 1 ELSE 0 END) AS recurrente,
               SUM(CASE WHEN UPPER(descripcion) LIKE '%CONVENIO%'
                        THEN 1 ELSE 0 END) AS convenio,
               SUM(CASE WHEN UPPER(descripcion) LIKE '%INSCRIPC%'
                        THEN 1 ELSE 0 END) AS inscripcion_en_descripcion
            FROM purchase_events
        """)[0]

        # Cruzar el tipo operativo con el texto de producto. '12 MESES' en
        # un contrato puede describir plazo, NO meses prepagados.
        by_type_signals = _query(conn, """
            SELECT tipo,
                   COUNT(*) AS movimientos,
                   SUM(CASE WHEN UPPER(descripcion) LIKE '%12 MESES%'
                            OR UPPER(descripcion) LIKE '%ANUAL%'
                            THEN 1 ELSE 0 END) AS texto_12_meses_o_anual,
                   SUM(CASE WHEN UPPER(descripcion) LIKE '%DOMICILIAD%'
                            THEN 1 ELSE 0 END) AS texto_domiciliado,
                   SUM(CASE WHEN UPPER(descripcion) LIKE '%RECURREN%'
                            THEN 1 ELSE 0 END) AS texto_recurrente,
                   SUM(CASE WHEN UPPER(descripcion) LIKE '%CONVENIO%'
                            THEN 1 ELSE 0 END) AS texto_convenio,
                   SUM(CASE WHEN UPPER(descripcion) LIKE '%INSCRIPC%'
                            THEN 1 ELSE 0 END) AS texto_inscripcion,
                   SUM(CASE WHEN estatus = 'CANCELADO'
                            THEN 1 ELSE 0 END) AS cancelados
            FROM purchase_events
            GROUP BY tipo
            ORDER BY movimientos DESC, tipo
        """)

        duplicated_purchase_months = _query(conn, """
            SELECT COUNT(*) AS socio_meses_con_varias_transacciones,
                   COALESCE(SUM(n - 1), 0) AS transacciones_adicionales,
                   COALESCE(MAX(n), 0) AS max_movimientos_mismo_socio_mes
            FROM (
                SELECT COUNT(*) AS n
                FROM purchase_events
                GROUP BY source_month, id_socio
                HAVING COUNT(*) > 1
            ) t
        """)[0]

        branch_change_signals = _query(conn, """
            SELECT COUNT(*) AS ids_socio_observados_en_varias_sucursales
            FROM (
                SELECT id_socio
                FROM purchase_events
                GROUP BY id_socio
                HAVING COUNT(DISTINCT sucursal) > 1
            ) t
        """)[0]

        monthly = _query(conn, """
            SELECT source_month AS mes, COUNT(*) AS movimientos_membresia,
                   COUNT(DISTINCT id_socio) AS ids_socio_distintos
            FROM purchase_events
            GROUP BY source_month
            ORDER BY source_month
        """)

    return {
        "advertencia": (
            "Las transacciones son señales comerciales; NO equivalen a "
            "mensualidades cubiertas o pagadas. No asignar tarifas ni rachas."
        ),
        "totales": totals,
        "por_tipo_y_estatus": by_type_status,
        "cruce_tipo_descripcion": by_type_signals,
        "senales_no_excluyentes_de_duracion_y_producto": period_signals,
        "repeticiones_mes_de_compra": duplicated_purchase_months,
        "movimientos_entre_sucursales": branch_change_signals,
        "por_mes": monthly,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output", type=Path,
                        help="Archivo JSON local, agregado y sin identificadores.")
    args = parser.parse_args()
    data = profile(args.database)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"[OUTPUT] {args.output}")
    print("[SUMMARY] " + json.dumps({
        **data["totales"],
        **data["repeticiones_mes_de_compra"],
        **data["movimientos_entre_sucursales"],
    }, ensure_ascii=False))
    print("[TIPOS_ESTADOS] " + json.dumps(
        data["por_tipo_y_estatus"], ensure_ascii=False,
    ))
    print("[CRUCE_TIPO_DESCRIPCION] " + json.dumps(
        data["cruce_tipo_descripcion"], ensure_ascii=False,
    ))
    print("[SEÑALES_PRODUCTO] " + json.dumps(
        data["senales_no_excluyentes_de_duracion_y_producto"],
        ensure_ascii=False,
    ))
    print("[NOTA] No se han calculado vigencias ni rachas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
