"""fix branch mappings and permanently remove la viga

Revision ID: c9f21d7a4b30
Revises: c81b2e6a4f90
Create Date: 2026-08-04 14:45:00

"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any

from alembic import op
import sqlalchemy as sa


revision = "c9f21d7a4b30"
down_revision = "c81b2e6a4f90"
branch_labels = None
depends_on = None


_EXPECTED_REAL_BRANCHES = {
    23: "TLALNEPANTLA",
    24: "METEPEC",
    25: "SALTILLO VILLALTA",
    26: "SERRANIA",
}

_CORRECT_CATALOG_MAPPING = {
    "TLALNEPANTLA": (23, 23),
    "SALTILLO_VILLALTA": (25, 24),
    "METEPEC": (24, 25),
    "SERRANIA": (26, 26),
}

_CORRECT_RAW_MAPPING = {
    "TLALNEPANTLA": 23,
    "SALTILLO VILLALTA": 25,
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


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()

    raise TypeError(
        "Tipo no serializable para payload_hash: "
        f"{type(value).__name__}"
    )


def _canonical_json_hash(
    payload: dict[str, Any],
) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


def _public_base_tables_with_column(
    connection,
    column_name: str,
) -> list[str]:
    rows = connection.execute(
        sa.text(
            """
            SELECT DISTINCT
                columns.table_name
            FROM information_schema.columns
                AS columns
            INNER JOIN information_schema.tables
                AS tables
                ON tables.table_schema
                   = columns.table_schema
               AND tables.table_name
                   = columns.table_name
            WHERE columns.table_schema = 'public'
              AND columns.column_name = :column_name
              AND tables.table_type = 'BASE TABLE'
            ORDER BY columns.table_name
            """
        ),
        {
            "column_name": column_name,
        },
    ).scalars().all()

    return [
        str(table_name)
        for table_name in rows
    ]


def _assert_reference_data(connection) -> None:
    rows = connection.execute(
        sa.text(
            """
            SELECT
                sucursal_id,
                sucursal
            FROM sucursales
            WHERE sucursal_id IN (23, 24, 25, 26)
            ORDER BY sucursal_id
            """
        )
    ).mappings().all()

    actual_branches = {
        int(row["sucursal_id"]): _normalize_text(
            row["sucursal"]
        )
        for row in rows
    }

    if actual_branches != _EXPECTED_REAL_BRANCHES:
        raise RuntimeError(
            "Las sucursales reales 23–26 no "
            "coinciden con el contrato esperado. "
            f"Actual={actual_branches!r}"
        )

    catalog_rows = connection.execute(
        sa.text(
            """
            SELECT sucursal_canon
            FROM track_branch_catalog
            WHERE sucursal_canon IN (
                'TLALNEPANTLA',
                'SALTILLO_VILLALTA',
                'METEPEC',
                'SERRANIA'
            )
            """
        )
    ).scalars().all()

    actual_catalog = {
        str(value)
        for value in catalog_rows
    }

    expected_catalog = set(
        _CORRECT_CATALOG_MAPPING
    )

    if actual_catalog != expected_catalog:
        raise RuntimeError(
            "Faltan sucursales canónicas "
            "requeridas. "
            f"Actual={actual_catalog!r}"
        )

    unexpected_members = connection.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM routine_control_members
            WHERE source_system = 'gasca'
              AND regexp_replace(
                    UPPER(
                        BTRIM(source_branch_name)
                    ),
                    '[^A-Z0-9]+',
                    '_',
                    'g'
                  ) = 'LA_VIGA'
            """
        )
    ).scalar_one()

    if int(unexpected_members) != 0:
        raise RuntimeError(
            "Aparecieron miembros Gasca de LA_VIGA "
            "después del precheck. "
            f"Filas={unexpected_members}"
        )

    unexpected_detail_rows = connection.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM
                ventas_nuevos_socios_detalle_snapshot_rows
            WHERE regexp_replace(
                    UPPER(BTRIM(sucursal_raw)),
                    '[^A-Z0-9]+',
                    '_',
                    'g'
                  ) = 'LA_VIGA'
            """
        )
    ).scalar_one()

    if int(unexpected_detail_rows) != 0:
        raise RuntimeError(
            "Aparecieron ventas detalle de "
            "LA_VIGA después del precheck. "
            f"Filas={unexpected_detail_rows}"
        )


def _purge_la_viga_canonical_data(
    connection,
) -> None:
    preparer = (
        connection.dialect.identifier_preparer
    )

    tables = _public_base_tables_with_column(
        connection,
        "sucursal_canon",
    )

    excluded_tables = {
        "track_branch_catalog",
        "track_branch_aliases",
    }

    for table_name in tables:
        if table_name in excluded_tables:
            continue

        quoted_table = preparer.quote(
            table_name
        )
        quoted_column = preparer.quote(
            "sucursal_canon"
        )

        expression = (
            _canonical_branch_expression(
                quoted_column
            )
        )

        connection.execute(
            sa.text(
                f"""
                DELETE FROM {quoted_table}
                WHERE {expression} = 'LA_VIGA'
                """
            )
        )

    connection.execute(
        sa.text(
            """
            DELETE FROM track_branch_aliases
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
    )

    connection.execute(
        sa.text(
            """
            DELETE FROM track_branch_catalog
            WHERE regexp_replace(
                    UPPER(BTRIM(sucursal_canon)),
                    '[^A-Z0-9]+',
                    '_',
                    'g'
                  ) = 'LA_VIGA'
            """
        )
    )


def _apply_catalog_mapping(
    connection,
) -> None:
    connection.execute(
        sa.text(
            """
            UPDATE track_branch_catalog
            SET display_order = CASE
                WHEN sucursal_canon
                     = 'TLALNEPANTLA'
                    THEN -201
                WHEN sucursal_canon
                     = 'SALTILLO_VILLALTA'
                    THEN -202
                WHEN sucursal_canon
                     = 'METEPEC'
                    THEN -203
                WHEN sucursal_canon
                     = 'SERRANIA'
                    THEN -204
                ELSE display_order
            END
            WHERE sucursal_canon IN (
                'TLALNEPANTLA',
                'SALTILLO_VILLALTA',
                'METEPEC',
                'SERRANIA'
            )
            """
        )
    )

    parameters = [
        {
            "sucursal_canon": canon,
            "sucursal_id": branch_id,
            "display_order": display_order,
        }
        for (
            canon,
            (
                branch_id,
                display_order,
            ),
        ) in _CORRECT_CATALOG_MAPPING.items()
    ]

    connection.execute(
        sa.text(
            """
            UPDATE track_branch_catalog
            SET
                sucursal_id = :sucursal_id,
                display_order = :display_order
            WHERE sucursal_canon
                  = :sucursal_canon
            """
        ),
        parameters,
    )


def _repair_routine_members(
    connection,
) -> None:
    parameters = [
        {
            "raw_branch_name": raw_name,
            "sucursal_id": branch_id,
        }
        for raw_name, branch_id
        in _CORRECT_RAW_MAPPING.items()
    ]

    connection.execute(
        sa.text(
            """
            UPDATE routine_control_members
            SET
                sucursal_id = :sucursal_id,
                updated_at = now()
            WHERE source_system = 'gasca'
              AND UPPER(
                    BTRIM(source_branch_name)
                  ) = :raw_branch_name
              AND sucursal_id IS DISTINCT FROM
                  :sucursal_id
            """
        ),
        parameters,
    )

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
              AND UPPER(
                    BTRIM(source_branch_name)
                  ) IN (
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
            "external_member_id": (
                row["external_member_id"]
            ),
            "external_sale_id": (
                row["external_sale_id"]
            ),
            "source_branch_name": (
                row["source_branch_name"]
            ),
            "sucursal_id": row["sucursal_id"],
            "member_name": row["member_name"],
            "email_original": (
                row["email_original"]
            ),
            "email_normalized": (
                row["email_normalized"]
            ),
            "phone_original": (
                row["phone_original"]
            ),
            "phone_normalized": (
                row["phone_normalized"]
            ),
            "sale_date": row["sale_date"],
        }

        updates.append(
            {
                "member_id": int(row["id"]),
                "payload_hash": (
                    _canonical_json_hash(
                        operational_payload
                    )
                ),
            }
        )

    if updates:
        connection.execute(
            sa.text(
                """
                UPDATE routine_control_members
                SET
                    payload_hash = :payload_hash
                WHERE id = :member_id
                """
            ),
            updates,
        )


def _repair_ventas_detail(
    connection,
) -> None:
    parameters = [
        {
            "raw_branch_name": raw_name,
            "sucursal_id": branch_id,
        }
        for raw_name, branch_id
        in _CORRECT_RAW_MAPPING.items()
    ]

    connection.execute(
        sa.text(
            """
            UPDATE
                ventas_nuevos_socios_detalle_snapshot_rows
            SET
                sucursal_id = :sucursal_id,
                updated_at = now()
            WHERE UPPER(
                    BTRIM(sucursal_raw)
                  ) = :raw_branch_name
              AND sucursal_id IS DISTINCT FROM
                  :sucursal_id
            """
        ),
        parameters,
    )

    # row_hash no incluye sucursal_id.
    # Se calcula únicamente con campos RAW.


def _assert_result(connection) -> None:
    rows = connection.execute(
        sa.text(
            """
            SELECT
                sucursal_canon,
                sucursal_id,
                display_order
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

    actual_catalog = {
        str(row["sucursal_canon"]): (
            int(row["sucursal_id"]),
            int(row["display_order"]),
        )
        for row in rows
    }

    if (
        actual_catalog
        != _CORRECT_CATALOG_MAPPING
    ):
        raise RuntimeError(
            "El catálogo no quedó con el mapeo "
            "esperado. "
            f"Actual={actual_catalog!r}"
        )

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

    if int(la_viga_catalog) != 0:
        raise RuntimeError(
            "LA_VIGA permanece en el catálogo."
        )

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

    if int(la_viga_aliases) != 0:
        raise RuntimeError(
            "Persisten aliases de LA_VIGA."
        )

    member_mismatches = connection.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM routine_control_members AS member
            INNER JOIN (
                VALUES
                    ('TLALNEPANTLA', 23),
                    ('SALTILLO VILLALTA', 25),
                    ('METEPEC', 24),
                    ('SERRANIA', 26)
            ) AS expected(
                raw_branch_name,
                sucursal_id
            )
                ON UPPER(
                    BTRIM(
                        member.source_branch_name
                    )
                   ) = expected.raw_branch_name
            WHERE member.source_system = 'gasca'
              AND member.sucursal_id
                  IS DISTINCT FROM
                  expected.sucursal_id
            """
        )
    ).scalar_one()

    if int(member_mismatches) != 0:
        raise RuntimeError(
            "Persisten miembros con sucursal "
            "incorrecta. "
            f"Filas={member_mismatches}"
        )

    detail_mismatches = connection.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM
                ventas_nuevos_socios_detalle_snapshot_rows
                AS detail
            INNER JOIN (
                VALUES
                    ('TLALNEPANTLA', 23),
                    ('SALTILLO VILLALTA', 25),
                    ('METEPEC', 24),
                    ('SERRANIA', 26)
            ) AS expected(
                raw_branch_name,
                sucursal_id
            )
                ON UPPER(
                    BTRIM(detail.sucursal_raw)
                   ) = expected.raw_branch_name
            WHERE detail.sucursal_id
                  IS DISTINCT FROM
                  expected.sucursal_id
            """
        )
    ).scalar_one()

    if int(detail_mismatches) != 0:
        raise RuntimeError(
            "Persisten ventas detalle con "
            "sucursal incorrecta. "
            f"Filas={detail_mismatches}"
        )

    preparer = (
        connection.dialect.identifier_preparer
    )

    remaining: list[str] = []

    for table_name in (
        _public_base_tables_with_column(
            connection,
            "sucursal_canon",
        )
    ):
        if table_name == "track_branch_catalog":
            continue

        quoted_table = preparer.quote(
            table_name
        )
        quoted_column = preparer.quote(
            "sucursal_canon"
        )

        expression = (
            _canonical_branch_expression(
                quoted_column
            )
        )

        count = connection.execute(
            sa.text(
                f"""
                SELECT COUNT(*)
                FROM {quoted_table}
                WHERE {expression} = 'LA_VIGA'
                """
            )
        ).scalar_one()

        if int(count) != 0:
            remaining.append(
                f"{table_name}={count}"
            )

    if remaining:
        raise RuntimeError(
            "Persisten datos canónicos de "
            "LA_VIGA. "
            f"Tablas={remaining!r}"
        )


def upgrade() -> None:
    connection = op.get_bind()

    _assert_reference_data(connection)

    _purge_la_viga_canonical_data(
        connection
    )

    _apply_catalog_mapping(connection)

    _repair_routine_members(connection)

    _repair_ventas_detail(connection)

    _assert_result(connection)


def downgrade() -> None:
    raise RuntimeError(
        "La migración c9f21d7a4b30 es "
        "irreversible: elimina definitivamente "
        "datos canónicos y operativos de "
        "LA_VIGA."
    )
