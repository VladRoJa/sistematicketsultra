"""canonicalize branch ids 23 26

Revision ID: a7d4e2c91f63
Revises: c9f21d7a4b30
Create Date: 2026-08-08

Canonical business identity:
23 = Tlalnepantla
24 = Saltillo Villalta
25 = Metepec
26 = Serrania

The migration preserves business identity while swapping the physical IDs
24/25. It moves every live FK to temporary parent rows first so composite
unique constraints never see Metepec and Villalta occupying the same ID.

RAW/text branch names are not rewritten.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any

from alembic import op
import sqlalchemy as sa


revision = "a7d4e2c91f63"
down_revision = "c9f21d7a4b30"
branch_labels = None
depends_on = None


_PREVIOUS_STATE = {
    23: "TLALNEPANTLA",
    24: "METEPEC",
    25: "SALTILLO VILLALTA",
    26: "SERRANIA",
}

_FINAL_STATE = {
    23: "TLALNEPANTLA",
    24: "SALTILLO VILLALTA",
    25: "METEPEC",
    26: "SERRANIA",
}

_PREVIOUS_ORDEN_APERTURA = {
    23: 25,
    24: 23,
    25: 24,
    26: 26,
}

_FINAL_ORDEN_APERTURA = {
    23: 23,
    24: 24,
    25: 25,
    26: 26,
}

_PREVIOUS_TRACK_CATALOG = {
    "TLALNEPANTLA": (23, 23),
    "SALTILLO_VILLALTA": (25, 24),
    "METEPEC": (24, 25),
    "SERRANIA": (26, 26),
}

_FINAL_TRACK_CATALOG = {
    "TLALNEPANTLA": (23, 23),
    "SALTILLO_VILLALTA": (24, 24),
    "METEPEC": (25, 25),
    "SERRANIA": (26, 26),
}

_TEMP_BY_OLD_ID = {
    24: -940024,
    25: -940025,
}

_FINAL_BY_OLD_ID = {
    24: 25,
    25: 24,
}

_EXPECTED_SUCURSALES_COLUMNS = [
    "sucursal_id",
    "serie",
    "sucursal",
    "estado",
    "municipio",
    "direccion",
    "orden_apertura",
    "operational_status",
]

_ALLOWED_NON_FK_NUMERIC_BRANCH_COLUMNS = {
    ("public", "track_fact_ingresos_daily", "sucursal_id"),
}


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().upper().split())


def _canonical_branch_expression(column_name: str) -> str:
    return f"""
        regexp_replace(
            UPPER(BTRIM(CAST({column_name} AS text))),
            '[^A-Z0-9]+',
            '_',
            'g'
        )
    """


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(
        "Tipo no serializable para payload_hash: "
        f"{type(value).__name__}"
    )


def _canonical_json_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _table_exists(connection, table_name: str) -> bool:
    value = connection.execute(
        sa.text("SELECT to_regclass(:table_name)"),
        {"table_name": f"public.{table_name}"},
    ).scalar_one()
    return value is not None


def _branch_state(connection) -> dict[int, str]:
    rows = connection.execute(
        sa.text(
            """
            SELECT sucursal_id, sucursal
            FROM sucursales
            WHERE sucursal_id IN (23, 24, 25, 26)
            ORDER BY sucursal_id
            """
        )
    ).mappings().all()
    return {
        int(row["sucursal_id"]): _normalize_text(row["sucursal"])
        for row in rows
    }


def _orden_apertura_state(connection) -> dict[int, int]:
    rows = connection.execute(
        sa.text(
            """
            SELECT sucursal_id, orden_apertura
            FROM sucursales
            WHERE sucursal_id IN (23, 24, 25, 26)
            ORDER BY sucursal_id
            """
        )
    ).mappings().all()
    result: dict[int, int] = {}
    for row in rows:
        if row["orden_apertura"] is None:
            raise RuntimeError(
                "orden_apertura inesperadamente NULL para "
                f"sucursal_id={row['sucursal_id']}"
            )
        result[int(row["sucursal_id"])] = int(row["orden_apertura"])
    return result


def _track_catalog_state(connection) -> dict[str, tuple[int, int]]:
    rows = connection.execute(
        sa.text(
            """
            SELECT sucursal_canon, sucursal_id, display_order
            FROM track_branch_catalog
            WHERE sucursal_canon IN (
                'TLALNEPANTLA',
                'SALTILLO_VILLALTA',
                'METEPEC',
                'SERRANIA'
            )
            """
        )
    ).mappings().all()
    result: dict[str, tuple[int, int]] = {}
    for row in rows:
        if row["sucursal_id"] is None or row["display_order"] is None:
            raise RuntimeError(
                "Track catalog contiene NULL en una sucursal canonica requerida."
            )
        result[str(row["sucursal_canon"])] = (
            int(row["sucursal_id"]),
            int(row["display_order"]),
        )
    return result


def _assert_parent_schema(connection) -> None:
    rows = connection.execute(
        sa.text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'sucursales'
            ORDER BY ordinal_position
            """
        )
    ).scalars().all()
    actual = [str(value) for value in rows]
    if actual != _EXPECTED_SUCURSALES_COLUMNS:
        raise RuntimeError(
            "La tabla sucursales cambio respecto al esquema auditado. "
            f"Actual={actual!r}"
        )


def _foreign_keys_to_sucursales(connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        sa.text(
            """
            SELECT
                child_ns.nspname AS schema_name,
                child.relname AS table_name,
                con.conname AS constraint_name,
                cardinality(con.conkey) AS child_column_count,
                cardinality(con.confkey) AS parent_column_count,
                child_att.attname AS child_column,
                parent_att.attname AS parent_column
            FROM pg_constraint AS con
            INNER JOIN pg_class AS child
                ON child.oid = con.conrelid
            INNER JOIN pg_namespace AS child_ns
                ON child_ns.oid = child.relnamespace
            INNER JOIN pg_class AS parent
                ON parent.oid = con.confrelid
            INNER JOIN pg_namespace AS parent_ns
                ON parent_ns.oid = parent.relnamespace
            LEFT JOIN pg_attribute AS child_att
                ON child_att.attrelid = child.oid
               AND child_att.attnum = con.conkey[1]
            LEFT JOIN pg_attribute AS parent_att
                ON parent_att.attrelid = parent.oid
               AND parent_att.attnum = con.confkey[1]
            WHERE con.contype = 'f'
              AND parent_ns.nspname = 'public'
              AND parent.relname = 'sucursales'
            ORDER BY child_ns.nspname, child.relname, con.conname
            """
        )
    ).mappings().all()
    result: list[dict[str, Any]] = []
    for row in rows:
        child_count = int(row["child_column_count"] or 0)
        parent_count = int(row["parent_column_count"] or 0)
        if (
            child_count != 1
            or parent_count != 1
            or row["parent_column"] != "sucursal_id"
        ):
            raise RuntimeError(
                "Se encontro una FK no soportada hacia sucursales. "
                f"Constraint={row['constraint_name']!r}, "
                f"child_columns={child_count}, "
                f"parent_columns={parent_count}, "
                f"parent_column={row['parent_column']!r}"
            )
        result.append(dict(row))
    return result


def _qualified_table(connection, schema_name: str, table_name: str) -> str:
    preparer = connection.dialect.identifier_preparer
    return (
        f"{preparer.quote_schema(schema_name)}."
        f"{preparer.quote(table_name)}"
    )


def _move_fk_references(
    connection,
    foreign_keys: list[dict[str, Any]],
    old_id: int,
    new_id: int,
) -> None:
    preparer = connection.dialect.identifier_preparer
    for fk in foreign_keys:
        table = _qualified_table(
            connection,
            str(fk["schema_name"]),
            str(fk["table_name"]),
        )
        column = preparer.quote(str(fk["child_column"]))
        connection.execute(
            sa.text(
                f"""
                UPDATE {table}
                SET {column} = :new_id
                WHERE {column} = :old_id
                """
            ),
            {"old_id": old_id, "new_id": new_id},
        )


def _assert_temp_ids_unused(
    connection,
    foreign_keys: list[dict[str, Any]],
) -> None:
    temp_24 = _TEMP_BY_OLD_ID[24]
    temp_25 = _TEMP_BY_OLD_ID[25]
    parent_count = connection.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM sucursales
            WHERE sucursal_id IN (:temp_24, :temp_25)
            """
        ),
        {"temp_24": temp_24, "temp_25": temp_25},
    ).scalar_one()
    if int(parent_count) != 0:
        raise RuntimeError("Los IDs temporales ya existen en sucursales.")

    preparer = connection.dialect.identifier_preparer
    for fk in foreign_keys:
        table = _qualified_table(
            connection,
            str(fk["schema_name"]),
            str(fk["table_name"]),
        )
        column = preparer.quote(str(fk["child_column"]))
        count = connection.execute(
            sa.text(
                f"""
                SELECT COUNT(*)
                FROM {table}
                WHERE {column} IN (:temp_24, :temp_25)
                """
            ),
            {"temp_24": temp_24, "temp_25": temp_25},
        ).scalar_one()
        if int(count) != 0:
            raise RuntimeError(
                "Un ID temporal ya esta referenciado. "
                f"Tabla={fk['table_name']!r}, "
                f"columna={fk['child_column']!r}, filas={count}"
            )


def _assert_no_unmanaged_numeric_branch_refs(
    connection,
    foreign_keys: list[dict[str, Any]],
) -> None:
    fk_columns = {
        (
            str(row["schema_name"]),
            str(row["table_name"]),
            str(row["child_column"]),
        )
        for row in foreign_keys
    }
    candidates = connection.execute(
        sa.text(
            """
            SELECT table_schema, table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND column_name LIKE '%sucursal_id%'
              AND data_type IN ('smallint', 'integer', 'bigint')
            ORDER BY table_schema, table_name, column_name
            """
        )
    ).mappings().all()
    preparer = connection.dialect.identifier_preparer
    unmanaged: list[str] = []
    for row in candidates:
        key = (
            str(row["table_schema"]),
            str(row["table_name"]),
            str(row["column_name"]),
        )
        if key == ("public", "sucursales", "sucursal_id"):
            continue
        if key in fk_columns:
            continue
        table = _qualified_table(connection, key[0], key[1])
        column = preparer.quote(key[2])
        count = connection.execute(
            sa.text(
                f"""
                SELECT COUNT(*)
                FROM {table}
                WHERE {column} IN (24, 25, :temp_24, :temp_25)
                """
            ),
            {
                "temp_24": _TEMP_BY_OLD_ID[24],
                "temp_25": _TEMP_BY_OLD_ID[25],
            },
        ).scalar_one()
        if int(count) == 0:
            continue
        if key in _ALLOWED_NON_FK_NUMERIC_BRANCH_COLUMNS:
            continue
        unmanaged.append(f"{key[0]}.{key[1]}.{key[2]}={int(count)}")
    if unmanaged:
        raise RuntimeError(
            "Existen referencias numericas de sucursal sin FK que la "
            "migracion no puede reinterpretar automaticamente. "
            f"Columnas={unmanaged!r}"
        )


def _clone_parent_to_temp(connection, old_id: int, temp_id: int) -> None:
    result = connection.execute(
        sa.text(
            """
            INSERT INTO sucursales (
                sucursal_id,
                serie,
                sucursal,
                estado,
                municipio,
                direccion,
                orden_apertura,
                operational_status
            )
            SELECT
                :temp_id,
                serie,
                sucursal,
                estado,
                municipio,
                direccion,
                NULL,
                operational_status
            FROM sucursales
            WHERE sucursal_id = :old_id
            """
        ),
        {"old_id": old_id, "temp_id": temp_id},
    )
    if result.rowcount != 1:
        raise RuntimeError(
            "No se pudo clonar exactamente una sucursal al ID temporal. "
            f"old_id={old_id}, temp_id={temp_id}, rowcount={result.rowcount}"
        )


def _clone_temp_to_final(connection, temp_id: int, final_id: int) -> None:
    result = connection.execute(
        sa.text(
            """
            INSERT INTO sucursales (
                sucursal_id,
                serie,
                sucursal,
                estado,
                municipio,
                direccion,
                orden_apertura,
                operational_status
            )
            SELECT
                :final_id,
                serie,
                sucursal,
                estado,
                municipio,
                direccion,
                NULL,
                operational_status
            FROM sucursales
            WHERE sucursal_id = :temp_id
            """
        ),
        {"temp_id": temp_id, "final_id": final_id},
    )
    if result.rowcount != 1:
        raise RuntimeError(
            "No se pudo clonar exactamente una sucursal temporal a su ID final. "
            f"temp_id={temp_id}, final_id={final_id}, rowcount={result.rowcount}"
        )


def _set_final_orden_apertura(connection) -> None:
    connection.execute(
        sa.text(
            """
            UPDATE sucursales
            SET orden_apertura = NULL
            WHERE sucursal_id IN (23, 24, 25, 26)
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE sucursales
            SET orden_apertura = CASE sucursal_id
                WHEN 23 THEN 23
                WHEN 24 THEN 24
                WHEN 25 THEN 25
                WHEN 26 THEN 26
                ELSE orden_apertura
            END
            WHERE sucursal_id IN (23, 24, 25, 26)
            """
        )
    )


def _repair_legacy_track_fact(connection) -> None:
    if not _table_exists(connection, "track_fact_ingresos_daily"):
        return
    expression = _canonical_branch_expression("sucursal_name")
    connection.execute(
        sa.text(
            f"""
            UPDATE track_fact_ingresos_daily
            SET sucursal_id = CASE
                WHEN {expression} = 'TLALNEPANTLA' THEN 23
                WHEN {expression} = 'SALTILLO_VILLALTA' THEN 24
                WHEN {expression} = 'METEPEC' THEN 25
                WHEN {expression} = 'SERRANIA' THEN 26
                WHEN {expression} = 'LA_VIGA' THEN NULL
                ELSE sucursal_id
            END
            WHERE {expression} IN (
                'TLALNEPANTLA',
                'SALTILLO_VILLALTA',
                'METEPEC',
                'SERRANIA',
                'LA_VIGA'
            )
            """
        )
    )


def _rebuild_routine_member_hashes(connection) -> None:
    rows = connection.execute(
        sa.text(
            """
            SELECT
                id,
                external_member_id,
                external_sale_id,
                source_branch_name,
                sucursal_id,
                member_name,
                email_original,
                email_normalized,
                phone_original,
                phone_normalized,
                sale_date
            FROM routine_control_members
            WHERE source_system = 'gasca'
              AND UPPER(BTRIM(source_branch_name)) IN (
                    'TLALNEPANTLA',
                    'SALTILLO VILLALTA',
                    'METEPEC',
                    'SERRANIA'
                  )
            ORDER BY id
            """
        )
    ).mappings().all()
    updates: list[dict[str, Any]] = []
    for row in rows:
        operational_payload = {
            "external_member_id": row["external_member_id"],
            "external_sale_id": row["external_sale_id"],
            "source_branch_name": row["source_branch_name"],
            "sucursal_id": row["sucursal_id"],
            "member_name": row["member_name"],
            "email_original": row["email_original"],
            "email_normalized": row["email_normalized"],
            "phone_original": row["phone_original"],
            "phone_normalized": row["phone_normalized"],
            "sale_date": row["sale_date"],
        }
        updates.append(
            {
                "member_id": int(row["id"]),
                "payload_hash": _canonical_json_hash(operational_payload),
            }
        )
    if updates:
        connection.execute(
            sa.text(
                """
                UPDATE routine_control_members
                SET payload_hash = :payload_hash
                WHERE id = :member_id
                """
            ),
            updates,
        )


def _assert_no_temp_state(
    connection,
    foreign_keys: list[dict[str, Any]],
) -> None:
    temp_24 = _TEMP_BY_OLD_ID[24]
    temp_25 = _TEMP_BY_OLD_ID[25]
    count = connection.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM sucursales
            WHERE sucursal_id IN (:temp_24, :temp_25)
            """
        ),
        {"temp_24": temp_24, "temp_25": temp_25},
    ).scalar_one()
    if int(count) != 0:
        raise RuntimeError("Quedaron padres temporales en sucursales.")
    preparer = connection.dialect.identifier_preparer
    for fk in foreign_keys:
        table = _qualified_table(
            connection,
            str(fk["schema_name"]),
            str(fk["table_name"]),
        )
        column = preparer.quote(str(fk["child_column"]))
        count = connection.execute(
            sa.text(
                f"""
                SELECT COUNT(*)
                FROM {table}
                WHERE {column} IN (:temp_24, :temp_25)
                """
            ),
            {"temp_24": temp_24, "temp_25": temp_25},
        ).scalar_one()
        if int(count) != 0:
            raise RuntimeError(
                "Quedaron referencias a IDs temporales. "
                f"Tabla={fk['table_name']!r}, "
                f"columna={fk['child_column']!r}, filas={count}"
            )


def _assert_la_viga_absent(connection) -> None:
    la_viga_sucursales = connection.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM sucursales
            WHERE regexp_replace(
                    UPPER(BTRIM(sucursal)),
                    '[^A-Z0-9]+',
                    '_',
                    'g'
                  ) = 'LA_VIGA'
            """
        )
    ).scalar_one()
    la_viga_catalog = connection.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM track_branch_catalog
            WHERE regexp_replace(
                    UPPER(BTRIM(sucursal_canon)),
                    '[^A-Z0-9]+',
                    '_',
                    'g'
                  ) = 'LA_VIGA'
            """
        )
    ).scalar_one()
    la_viga_aliases = connection.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM track_branch_aliases
            WHERE regexp_replace(
                    UPPER(BTRIM(raw_branch_name)),
                    '[^A-Z0-9]+',
                    '_',
                    'g'
                  ) = 'LA_VIGA'
               OR regexp_replace(
                    UPPER(BTRIM(sucursal_canon)),
                    '[^A-Z0-9]+',
                    '_',
                    'g'
                  ) = 'LA_VIGA'
            """
        )
    ).scalar_one()
    actual = {
        "sucursales": int(la_viga_sucursales),
        "track_branch_catalog": int(la_viga_catalog),
        "track_branch_aliases": int(la_viga_aliases),
    }
    if any(actual.values()):
        raise RuntimeError(
            "LA VIGA reaparecio en estructura operativa/canonica. "
            f"Actual={actual!r}"
        )


def _assert_routine_members(connection) -> None:
    mismatches = connection.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM routine_control_members AS member
            INNER JOIN (
                VALUES
                    ('TLALNEPANTLA', 23),
                    ('SALTILLO VILLALTA', 24),
                    ('METEPEC', 25),
                    ('SERRANIA', 26)
            ) AS expected(raw_branch_name, sucursal_id)
                ON UPPER(BTRIM(member.source_branch_name))
                   = expected.raw_branch_name
            WHERE member.source_system = 'gasca'
              AND member.sucursal_id IS DISTINCT FROM expected.sucursal_id
            """
        )
    ).scalar_one()
    if int(mismatches) != 0:
        raise RuntimeError(
            "Persisten routine_control_members con sucursal incorrecta. "
            f"Filas={mismatches}"
        )


def _assert_ventas_detail(connection) -> None:
    mismatches = connection.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM ventas_nuevos_socios_detalle_snapshot_rows AS detail
            INNER JOIN (
                VALUES
                    ('TLALNEPANTLA', 23),
                    ('SALTILLO VILLALTA', 24),
                    ('METEPEC', 25),
                    ('SERRANIA', 26)
            ) AS expected(raw_branch_name, sucursal_id)
                ON UPPER(BTRIM(detail.sucursal_raw))
                   = expected.raw_branch_name
            WHERE detail.sucursal_id IS DISTINCT FROM expected.sucursal_id
            """
        )
    ).scalar_one()
    if int(mismatches) != 0:
        raise RuntimeError(
            "Persisten ventas detalle con sucursal incorrecta. "
            f"Filas={mismatches}"
        )


def _assert_opening_serrania(connection) -> None:
    mismatches = connection.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM openings
            WHERE opening_key = 'SERRANIA'
              AND sucursal_id IS DISTINCT FROM 26
            """
        )
    ).scalar_one()
    if int(mismatches) != 0:
        raise RuntimeError(
            "La apertura de Serrania perdio su sucursal_id=26. "
            f"Filas={mismatches}"
        )


def _assert_legacy_track_fact(connection) -> None:
    if not _table_exists(connection, "track_fact_ingresos_daily"):
        return
    expression = _canonical_branch_expression("sucursal_name")
    mismatches = connection.execute(
        sa.text(
            f"""
            SELECT COUNT(*)
            FROM track_fact_ingresos_daily
            WHERE ({expression} = 'TLALNEPANTLA'
                   AND sucursal_id IS DISTINCT FROM 23)
               OR ({expression} = 'SALTILLO_VILLALTA'
                   AND sucursal_id IS DISTINCT FROM 24)
               OR ({expression} = 'METEPEC'
                   AND sucursal_id IS DISTINCT FROM 25)
               OR ({expression} = 'SERRANIA'
                   AND sucursal_id IS DISTINCT FROM 26)
               OR ({expression} = 'LA_VIGA'
                   AND sucursal_id IS NOT NULL)
            """
        )
    ).scalar_one()
    if int(mismatches) != 0:
        raise RuntimeError(
            "track_fact_ingresos_daily no quedo con el contrato final. "
            f"Filas={mismatches}"
        )


def _assert_preconditions(connection) -> None:
    _assert_parent_schema(connection)
    actual_branches = _branch_state(connection)
    if actual_branches != _PREVIOUS_STATE:
        raise RuntimeError(
            "Las sucursales 23-26 no estan en el estado c9 esperado. "
            f"Actual={actual_branches!r}"
        )
    actual_order = _orden_apertura_state(connection)
    if actual_order != _PREVIOUS_ORDEN_APERTURA:
        raise RuntimeError(
            "orden_apertura no coincide con el estado c9 esperado. "
            f"Actual={actual_order!r}"
        )
    actual_catalog = _track_catalog_state(connection)
    if actual_catalog != _PREVIOUS_TRACK_CATALOG:
        raise RuntimeError(
            "Track catalog no coincide con el estado c9 esperado. "
            f"Actual={actual_catalog!r}"
        )
    _assert_la_viga_absent(connection)


def _assert_result(
    connection,
    foreign_keys: list[dict[str, Any]],
) -> None:
    actual_branches = _branch_state(connection)
    if actual_branches != _FINAL_STATE:
        raise RuntimeError(
            "sucursales no quedo con el contrato final. "
            f"Actual={actual_branches!r}"
        )
    actual_order = _orden_apertura_state(connection)
    if actual_order != _FINAL_ORDEN_APERTURA:
        raise RuntimeError(
            "orden_apertura no quedo con el contrato final. "
            f"Actual={actual_order!r}"
        )
    actual_catalog = _track_catalog_state(connection)
    if actual_catalog != _FINAL_TRACK_CATALOG:
        raise RuntimeError(
            "Track catalog no quedo con el contrato final. "
            f"Actual={actual_catalog!r}"
        )
    _assert_no_temp_state(connection, foreign_keys)
    _assert_la_viga_absent(connection)
    _assert_routine_members(connection)
    _assert_ventas_detail(connection)
    _assert_opening_serrania(connection)
    _assert_legacy_track_fact(connection)


def upgrade() -> None:
    connection = op.get_bind()
    _assert_preconditions(connection)

    foreign_keys = _foreign_keys_to_sucursales(connection)
    _assert_temp_ids_unused(connection, foreign_keys)
    _assert_no_unmanaged_numeric_branch_refs(connection, foreign_keys)

    for old_id, temp_id in _TEMP_BY_OLD_ID.items():
        _clone_parent_to_temp(connection, old_id, temp_id)

    for old_id, temp_id in _TEMP_BY_OLD_ID.items():
        _move_fk_references(
            connection,
            foreign_keys,
            old_id,
            temp_id,
        )

    deleted = connection.execute(
        sa.text("DELETE FROM sucursales WHERE sucursal_id IN (24, 25)")
    )
    if deleted.rowcount != 2:
        raise RuntimeError(
            "No se eliminaron exactamente los dos padres 24/25 previos. "
            f"rowcount={deleted.rowcount}"
        )

    for old_id, final_id in _FINAL_BY_OLD_ID.items():
        _clone_temp_to_final(
            connection,
            _TEMP_BY_OLD_ID[old_id],
            final_id,
        )

    for old_id, final_id in _FINAL_BY_OLD_ID.items():
        _move_fk_references(
            connection,
            foreign_keys,
            _TEMP_BY_OLD_ID[old_id],
            final_id,
        )

    connection.execute(
        sa.text(
            """
            DELETE FROM sucursales
            WHERE sucursal_id IN (:temp_24, :temp_25)
            """
        ),
        {
            "temp_24": _TEMP_BY_OLD_ID[24],
            "temp_25": _TEMP_BY_OLD_ID[25],
        },
    )

    _set_final_orden_apertura(connection)
    _repair_legacy_track_fact(connection)
    _rebuild_routine_member_hashes(connection)
    _assert_result(connection, foreign_keys)


def downgrade() -> None:
    raise RuntimeError(
        "La migracion a7d4e2c91f63 es irreversible: establece la identidad "
        "canonica oficial de sucursales 23-26."
    )
