"""bridge sucursal identity state before c9

Revision ID: f3a6c1d8e2b4
Revises: c81b2e6a4f90
Create Date: 2026-08-08

This migration formalizes the reference-data normalization that production
already had before c9f21d7a4b30 was executed.

It is intentionally state-aware:
- legacy local c81 state -> normalize to the pre-c9 reference state;
- already normalized pre-c9 identity -> reconcile/validate legacy-only artifacts;
- any other state -> fail closed.

It does NOT implement the final canonical 23/24/25/26 contract. That belongs
to a later migration after c9.
"""

from __future__ import annotations

from typing import Any

from alembic import op
import sqlalchemy as sa


revision = "f3a6c1d8e2b4"
down_revision = "c81b2e6a4f90"
branch_labels = None
depends_on = None


_LEGACY_LOCAL_STATE = {
    23: "METEPEC",
    24: "TLALNEPANTLA",
    25: "SALTILLO VILLALTA",
    26: "LA VIGA",
    1001: "SERRANIA",
}

_PRE_C9_STATE = {
    23: "TLALNEPANTLA",
    24: "METEPEC",
    25: "SALTILLO VILLALTA",
    26: "SERRANIA",
}

_TEMP_BY_OLD_ID = {
    23: -930023,
    24: -930024,
    1001: -931001,
}

_PRE_C9_TARGET_BY_OLD_ID = {
    23: 24,    # Metepec
    24: 23,    # Tlalnepantla
    1001: 26,  # Serrania
}

_PRE_C9_ORDEN_APERTURA = {
    23: 25,  # Tlalnepantla
    24: 23,  # Metepec
    25: 24,  # Saltillo Villalta
    26: 26,  # Serrania
}

_PRE_C9_NAME_TO_ID = {
    "TLALNEPANTLA": 23,
    "SALTILLO_VILLALTA": 25,
    "METEPEC": 24,
    "SERRANIA": 26,
}


def _normalize_text(value: Any) -> str:
    return " ".join(
        str(value or "").strip().upper().split()
    )


def _canonical_branch_expression(
    column_name: str,
) -> str:
    return f"""
        regexp_replace(
            UPPER(
                BTRIM(
                    CAST({column_name} AS text)
                )
            ),
            '[^A-Z0-9]+',
            '_',
            'g'
        )
    """


def _table_exists(
    connection,
    table_name: str,
) -> bool:
    value = connection.execute(
        sa.text(
            """
            SELECT to_regclass(:table_name)
            """
        ),
        {
            "table_name": f"public.{table_name}",
        },
    ).scalar_one()

    return value is not None


def _branch_state(
    connection,
) -> dict[int, str]:
    rows = connection.execute(
        sa.text(
            """
            SELECT
                sucursal_id,
                sucursal
            FROM sucursales
            WHERE sucursal_id IN (
                23, 24, 25, 26, 1001
            )
            ORDER BY sucursal_id
            """
        )
    ).mappings().all()

    return {
        int(row["sucursal_id"]): _normalize_text(
            row["sucursal"]
        )
        for row in rows
    }


def _classify_state(
    connection,
) -> str:
    actual = _branch_state(connection)

    if actual == _LEGACY_LOCAL_STATE:
        return "legacy_local"

    if actual == _PRE_C9_STATE:
        return "pre_c9"

    raise RuntimeError(
        "Estado de sucursales no reconocido por el bridge "
        "f3a6c1d8e2b4. "
        f"Actual={actual!r}"
    )


def _foreign_keys_to_sucursales(
    connection,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        sa.text(
            """
            SELECT
                child_ns.nspname AS schema_name,
                child.relname AS table_name,
                con.conname AS constraint_name,
                cardinality(con.conkey)
                    AS child_column_count,
                cardinality(con.confkey)
                    AS parent_column_count,
                child_att.attname AS child_column,
                parent_att.attname AS parent_column,
                con.confdeltype AS on_delete_code
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
            ORDER BY
                child_ns.nspname,
                child.relname,
                con.conname
            """
        )
    ).mappings().all()

    result: list[dict[str, Any]] = []

    for row in rows:
        child_count = int(
            row["child_column_count"] or 0
        )
        parent_count = int(
            row["parent_column_count"] or 0
        )

        if (
            child_count != 1
            or parent_count != 1
            or row["parent_column"] != "sucursal_id"
        ):
            raise RuntimeError(
                "El bridge encontró una FK compuesta o "
                "no compatible hacia sucursales. "
                f"Constraint={row['constraint_name']!r}, "
                f"child_columns={child_count}, "
                f"parent_columns={parent_count}, "
                f"parent_column={row['parent_column']!r}"
            )

        result.append(dict(row))

    return result


def _qualified_table(
    connection,
    schema_name: str,
    table_name: str,
) -> str:
    preparer = (
        connection.dialect.identifier_preparer
    )

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
    preparer = (
        connection.dialect.identifier_preparer
    )

    for fk in foreign_keys:
        table = _qualified_table(
            connection,
            str(fk["schema_name"]),
            str(fk["table_name"]),
        )
        column = preparer.quote(
            str(fk["child_column"])
        )

        connection.execute(
            sa.text(
                f"""
                UPDATE {table}
                SET {column} = :new_id
                WHERE {column} = :old_id
                """
            ),
            {
                "old_id": old_id,
                "new_id": new_id,
            },
        )


def _assert_temp_ids_unused(
    connection,
    foreign_keys: list[dict[str, Any]],
) -> None:
    temp_ids = tuple(
        _TEMP_BY_OLD_ID.values()
    )

    parent_count = connection.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM sucursales
            WHERE sucursal_id IN (
                :temp_1,
                :temp_2,
                :temp_3
            )
            """
        ),
        {
            "temp_1": temp_ids[0],
            "temp_2": temp_ids[1],
            "temp_3": temp_ids[2],
        },
    ).scalar_one()

    if int(parent_count) != 0:
        raise RuntimeError(
            "Uno de los IDs temporales del bridge "
            "ya existe en sucursales."
        )

    preparer = (
        connection.dialect.identifier_preparer
    )

    for fk in foreign_keys:
        table = _qualified_table(
            connection,
            str(fk["schema_name"]),
            str(fk["table_name"]),
        )
        column = preparer.quote(
            str(fk["child_column"])
        )

        count = connection.execute(
            sa.text(
                f"""
                SELECT COUNT(*)
                FROM {table}
                WHERE {column} IN (
                    :temp_1,
                    :temp_2,
                    :temp_3
                )
                """
            ),
            {
                "temp_1": temp_ids[0],
                "temp_2": temp_ids[1],
                "temp_3": temp_ids[2],
            },
        ).scalar_one()

        if int(count) != 0:
            raise RuntimeError(
                "Uno de los IDs temporales del bridge "
                "ya está referenciado. "
                f"Tabla={fk['table_name']!r}, "
                f"columna={fk['child_column']!r}, "
                f"filas={count}"
            )


def _insert_temp_parent(
    connection,
    old_id: int,
    temp_id: int,
) -> None:
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
        {
            "old_id": old_id,
            "temp_id": temp_id,
        },
    )

    if result.rowcount != 1:
        raise RuntimeError(
            "No se pudo crear exactamente una fila "
            "temporal de sucursal. "
            f"old_id={old_id}, temp_id={temp_id}, "
            f"rowcount={result.rowcount}"
        )


def _insert_final_parent_from_temp(
    connection,
    temp_id: int,
    target_id: int,
) -> None:
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
                :target_id,
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
        {
            "temp_id": temp_id,
            "target_id": target_id,
        },
    )

    if result.rowcount != 1:
        raise RuntimeError(
            "No se pudo crear exactamente una fila "
            "final desde el temporal. "
            f"temp_id={temp_id}, target_id={target_id}, "
            f"rowcount={result.rowcount}"
        )


def _assert_la_viga_parent_can_be_deleted(
    connection,
    foreign_keys: list[dict[str, Any]],
) -> None:
    preparer = (
        connection.dialect.identifier_preparer
    )

    safe_delete_codes = {
        "c",  # CASCADE
        "n",  # SET NULL
    }

    blocking: list[str] = []

    for fk in foreign_keys:
        table = _qualified_table(
            connection,
            str(fk["schema_name"]),
            str(fk["table_name"]),
        )
        column = preparer.quote(
            str(fk["child_column"])
        )

        count = connection.execute(
            sa.text(
                f"""
                SELECT COUNT(*)
                FROM {table}
                WHERE {column} = 26
                """
            )
        ).scalar_one()

        if (
            int(count) != 0
            and str(fk["on_delete_code"])
                not in safe_delete_codes
        ):
            blocking.append(
                f"{fk['table_name']}."
                f"{fk['child_column']}="
                f"{count} "
                f"(on_delete={fk['on_delete_code']})"
            )

    if blocking:
        raise RuntimeError(
            "LA VIGA todavía tiene referencias "
            "que no pueden eliminarse de forma "
            "semánticamente segura. "
            f"Referencias={blocking!r}"
        )


def _cleanup_legacy_local_tables(
    connection,
) -> None:
    if _table_exists(
        connection,
        "track_dim_sucursal",
    ):
        expression = (
            _canonical_branch_expression(
                "track_name"
            )
        )

        connection.execute(
            sa.text(
                f"""
                DELETE FROM track_dim_sucursal
                WHERE {expression} = 'LA_VIGA'
                """
            )
        )

    if _table_exists(
        connection,
        "track_fact_ingresos_daily",
    ):
        expression = (
            _canonical_branch_expression(
                "sucursal_name"
            )
        )

        connection.execute(
            sa.text(
                f"""
                UPDATE track_fact_ingresos_daily
                SET sucursal_id = CASE
                    WHEN {expression}
                         = 'TLALNEPANTLA'
                        THEN 23
                    WHEN {expression}
                         = 'SALTILLO_VILLALTA'
                        THEN 25
                    WHEN {expression}
                         = 'METEPEC'
                        THEN 24
                    WHEN {expression}
                         = 'SERRANIA'
                        THEN 26
                    WHEN {expression}
                         = 'LA_VIGA'
                        THEN NULL
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


def _set_pre_c9_orden_apertura(
    connection,
) -> None:
    connection.execute(
        sa.text(
            """
            UPDATE sucursales
            SET orden_apertura = NULL
            WHERE sucursal_id IN (
                23, 24, 25, 26
            )
            """
        )
    )

    connection.execute(
        sa.text(
            """
            UPDATE sucursales
            SET orden_apertura = CASE sucursal_id
                WHEN 23 THEN 25
                WHEN 24 THEN 23
                WHEN 25 THEN 24
                WHEN 26 THEN 26
                ELSE orden_apertura
            END
            WHERE sucursal_id IN (
                23, 24, 25, 26
            )
            """
        )
    )


def _assert_no_temp_references(
    connection,
    foreign_keys: list[dict[str, Any]],
) -> None:
    temp_ids = tuple(
        _TEMP_BY_OLD_ID.values()
    )

    preparer = (
        connection.dialect.identifier_preparer
    )

    for fk in foreign_keys:
        table = _qualified_table(
            connection,
            str(fk["schema_name"]),
            str(fk["table_name"]),
        )
        column = preparer.quote(
            str(fk["child_column"])
        )

        count = connection.execute(
            sa.text(
                f"""
                SELECT COUNT(*)
                FROM {table}
                WHERE {column} IN (
                    :temp_1,
                    :temp_2,
                    :temp_3
                )
                """
            ),
            {
                "temp_1": temp_ids[0],
                "temp_2": temp_ids[1],
                "temp_3": temp_ids[2],
            },
        ).scalar_one()

        if int(count) != 0:
            raise RuntimeError(
                "Quedaron referencias a IDs "
                "temporales del bridge. "
                f"Tabla={fk['table_name']!r}, "
                f"columna={fk['child_column']!r}, "
                f"filas={count}"
            )


def _assert_legacy_tables(
    connection,
) -> None:
    if _table_exists(
        connection,
        "track_dim_sucursal",
    ):
        expression = (
            _canonical_branch_expression(
                "track_name"
            )
        )

        la_viga = connection.execute(
            sa.text(
                f"""
                SELECT COUNT(*)
                FROM track_dim_sucursal
                WHERE {expression} = 'LA_VIGA'
                """
            )
        ).scalar_one()

        if int(la_viga) != 0:
            raise RuntimeError(
                "track_dim_sucursal todavía "
                "contiene LA VIGA."
            )

        mismatch = connection.execute(
            sa.text(
                f"""
                SELECT COUNT(*)
                FROM track_dim_sucursal
                WHERE (
                    {expression}
                        = 'TLALNEPANTLA'
                    AND sucursal_id
                        IS DISTINCT FROM 23
                )
                   OR (
                    {expression}
                        = 'SALTILLO_VILLALTA'
                    AND sucursal_id
                        IS DISTINCT FROM 25
                )
                   OR (
                    {expression}
                        = 'METEPEC'
                    AND sucursal_id
                        IS DISTINCT FROM 24
                )
                   OR (
                    {expression}
                        = 'SERRANIA'
                    AND sucursal_id
                        IS DISTINCT FROM 26
                )
                """
            )
        ).scalar_one()

        if int(mismatch) != 0:
            raise RuntimeError(
                "track_dim_sucursal no quedó "
                "con el estado pre-c9 esperado. "
                f"Filas={mismatch}"
            )

    if _table_exists(
        connection,
        "track_fact_ingresos_daily",
    ):
        expression = (
            _canonical_branch_expression(
                "sucursal_name"
            )
        )

        mismatch = connection.execute(
            sa.text(
                f"""
                SELECT COUNT(*)
                FROM track_fact_ingresos_daily
                WHERE (
                    {expression}
                        = 'TLALNEPANTLA'
                    AND sucursal_id
                        IS DISTINCT FROM 23
                )
                   OR (
                    {expression}
                        = 'SALTILLO_VILLALTA'
                    AND sucursal_id
                        IS DISTINCT FROM 25
                )
                   OR (
                    {expression}
                        = 'METEPEC'
                    AND sucursal_id
                        IS DISTINCT FROM 24
                )
                   OR (
                    {expression}
                        = 'SERRANIA'
                    AND sucursal_id
                        IS DISTINCT FROM 26
                )
                   OR (
                    {expression}
                        = 'LA_VIGA'
                    AND sucursal_id IS NOT NULL
                )
                """
            )
        ).scalar_one()

        if int(mismatch) != 0:
            raise RuntimeError(
                "track_fact_ingresos_daily no "
                "quedó con el estado pre-c9 "
                "esperado. "
                f"Filas={mismatch}"
            )


def _assert_pre_c9_result(
    connection,
    foreign_keys: list[dict[str, Any]],
) -> None:
    actual = _branch_state(connection)

    if actual != _PRE_C9_STATE:
        raise RuntimeError(
            "El bridge no dejó sucursales en "
            "el estado pre-c9 esperado. "
            f"Actual={actual!r}"
        )

    la_viga_rows = connection.execute(
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

    if int(la_viga_rows) != 0:
        raise RuntimeError(
            "LA VIGA todavía existe como "
            "sucursal operativa."
        )

    order_rows = connection.execute(
        sa.text(
            """
            SELECT
                sucursal_id,
                orden_apertura
            FROM sucursales
            WHERE sucursal_id IN (
                23, 24, 25, 26
            )
            ORDER BY sucursal_id
            """
        )
    ).mappings().all()

    actual_order = {
        int(row["sucursal_id"]): int(
            row["orden_apertura"]
        )
        for row in order_rows
    }

    if (
        actual_order
        != _PRE_C9_ORDEN_APERTURA
    ):
        raise RuntimeError(
            "orden_apertura no quedó con el "
            "estado pre-c9 de producción. "
            f"Actual={actual_order!r}"
        )

    temp_parent_count = connection.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM sucursales
            WHERE sucursal_id IN (
                :temp_1,
                :temp_2,
                :temp_3
            )
            """
        ),
        {
            "temp_1": _TEMP_BY_OLD_ID[23],
            "temp_2": _TEMP_BY_OLD_ID[24],
            "temp_3": _TEMP_BY_OLD_ID[1001],
        },
    ).scalar_one()

    if int(temp_parent_count) != 0:
        raise RuntimeError(
            "Quedaron sucursales temporales "
            "después del bridge."
        )

    _assert_no_temp_references(
        connection,
        foreign_keys,
    )

    _assert_legacy_tables(connection)


def _normalize_legacy_local_state(
    connection,
) -> None:
    foreign_keys = (
        _foreign_keys_to_sucursales(
            connection
        )
    )

    _assert_temp_ids_unused(
        connection,
        foreign_keys,
    )

    for old_id, temp_id in (
        _TEMP_BY_OLD_ID.items()
    ):
        _insert_temp_parent(
            connection,
            old_id,
            temp_id,
        )

    for old_id, temp_id in (
        _TEMP_BY_OLD_ID.items()
    ):
        _move_fk_references(
            connection,
            foreign_keys,
            old_id,
            temp_id,
        )

    _cleanup_legacy_local_tables(
        connection
    )

    _assert_la_viga_parent_can_be_deleted(
        connection,
        foreign_keys,
    )

    connection.execute(
        sa.text(
            """
            DELETE FROM sucursales
            WHERE sucursal_id IN (
                23, 24, 26, 1001
            )
            """
        )
    )

    for (
        old_id,
        target_id,
    ) in _PRE_C9_TARGET_BY_OLD_ID.items():
        temp_id = _TEMP_BY_OLD_ID[
            old_id
        ]

        _insert_final_parent_from_temp(
            connection,
            temp_id,
            target_id,
        )

    for (
        old_id,
        target_id,
    ) in _PRE_C9_TARGET_BY_OLD_ID.items():
        temp_id = _TEMP_BY_OLD_ID[
            old_id
        ]

        _move_fk_references(
            connection,
            foreign_keys,
            temp_id,
            target_id,
        )

    connection.execute(
        sa.text(
            """
            DELETE FROM sucursales
            WHERE sucursal_id IN (
                :temp_1,
                :temp_2,
                :temp_3
            )
            """
        ),
        {
            "temp_1": _TEMP_BY_OLD_ID[23],
            "temp_2": _TEMP_BY_OLD_ID[24],
            "temp_3": _TEMP_BY_OLD_ID[1001],
        },
    )

    _set_pre_c9_orden_apertura(
        connection
    )

    _cleanup_legacy_local_tables(
        connection
    )

    _assert_pre_c9_result(
        connection,
        foreign_keys,
    )


def upgrade() -> None:
    connection = op.get_bind()

    state = _classify_state(
        connection
    )

    if state == "pre_c9":
        foreign_keys = (
            _foreign_keys_to_sucursales(
                connection
            )
        )

        _set_pre_c9_orden_apertura(
            connection
        )

        _cleanup_legacy_local_tables(
            connection
        )

        _assert_pre_c9_result(
            connection,
            foreign_keys,
        )
        return

    if state != "legacy_local":
        raise RuntimeError(
            "Estado no soportado por el bridge."
        )

    _normalize_legacy_local_state(
        connection
    )


def downgrade() -> None:
    raise RuntimeError(
        "La migración f3a6c1d8e2b4 es "
        "irreversible: formaliza una "
        "normalización histórica de identidad "
        "de sucursales necesaria antes de c9."
    )
