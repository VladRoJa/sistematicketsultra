"""Asignar codigos internos a Air Bike de Metepec.

Revision ID: a9c4e2f1b7d3
Revises: f2c9a1d4e8b7
Create Date: 2026-09-11
"""

from alembic import op
import sqlalchemy as sa


revision = "a9c4e2f1b7d3"
down_revision = "f2c9a1d4e8b7"
branch_labels = None
depends_on = None


SUCURSAL_ID = 25
TARGET_CODES = ("25ABJW202", "25ABJW203")


def _target_ids(bind):
    rows = bind.execute(
        sa.text(
            """
            SELECT i.id
            FROM inventario_general i
            JOIN inventario_sucursal s
              ON s.inventario_id = i.id
            WHERE s.sucursal_id = :sucursal_id
              AND UPPER(TRIM(COALESCE(i.tipo, ''))) = 'APARATOS'
              AND UPPER(TRIM(COALESCE(i.nombre, ''))) = 'AIR BIKE'
              AND UPPER(TRIM(COALESCE(i.descripcion, ''))) = 'TH15K08'
              AND UPPER(TRIM(COALESCE(i.marca, ''))) = 'JW SPORTS'
              AND i.familia_equipo_id = 5
              AND i.categoria_inventario_id = 4
              AND (i.codigo_interno IS NULL OR TRIM(i.codigo_interno) = '')
              AND s.stock > 0
            ORDER BY i.id
            FOR UPDATE
            """
        ),
        {"sucursal_id": SUCURSAL_ID},
    ).fetchall()
    return [int(row[0]) for row in rows]


def upgrade():
    bind = op.get_bind()

    collisions = bind.execute(
        sa.text(
            """
            SELECT codigo_interno
            FROM inventario_general
            WHERE codigo_interno IN (:code_1, :code_2)
            ORDER BY codigo_interno
            """
        ),
        {"code_1": TARGET_CODES[0], "code_2": TARGET_CODES[1]},
    ).fetchall()

    if collisions:
        values = ", ".join(str(row[0]) for row in collisions)
        raise RuntimeError(
            f"No se pueden asignar codigos Air Bike Metepec; ya existen: {values}"
        )

    target_ids = _target_ids(bind)
    if len(target_ids) != 2:
        raise RuntimeError(
            "Se esperaban exactamente 2 Air Bike sin codigo en Metepec; "
            f"se encontraron {len(target_ids)}"
        )

    assignments = (
        (target_ids[0], "25ABJW202", "202"),
        (target_ids[1], "25ABJW203", "203"),
    )

    for inventory_id, code, equipment_number in assignments:
        bind.execute(
            sa.text(
                """
                UPDATE inventario_general
                SET codigo_interno = :code,
                    no_equipo = :equipment_number
                WHERE id = :inventory_id
                """
            ),
            {
                "inventory_id": inventory_id,
                "code": code,
                "equipment_number": equipment_number,
            },
        )


def downgrade():
    bind = op.get_bind()

    bind.execute(
        sa.text(
            """
            UPDATE inventario_general i
            SET codigo_interno = NULL,
                no_equipo = NULL
            FROM inventario_sucursal s
            WHERE s.inventario_id = i.id
              AND s.sucursal_id = :sucursal_id
              AND i.codigo_interno IN (:code_1, :code_2)
              AND UPPER(TRIM(COALESCE(i.nombre, ''))) = 'AIR BIKE'
              AND UPPER(TRIM(COALESCE(i.descripcion, ''))) = 'TH15K08'
              AND UPPER(TRIM(COALESCE(i.marca, ''))) = 'JW SPORTS'
              AND i.familia_equipo_id = 5
              AND i.categoria_inventario_id = 4
            """
        ),
        {
            "sucursal_id": SUCURSAL_ID,
            "code_1": TARGET_CODES[0],
            "code_2": TARGET_CODES[1],
        },
    )
