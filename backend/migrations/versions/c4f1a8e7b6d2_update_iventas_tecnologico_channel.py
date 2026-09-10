"""update iVentas Tecnologico to current channel

Revision ID: c4f1a8e7b6d2
Revises: e3f6a9b1c5d7
Create Date: 2026-09-10

iVentas confirmó que:

- tecnologico   = canal anterior
- tecnologico-2 = canal actual

El destino Suite/Track permanece TEC_MXL.
"""

from alembic import op
import sqlalchemy as sa


revision = "c4f1a8e7b6d2"
down_revision = "e3f6a9b1c5d7"
branch_labels = None
depends_on = None


SOURCE_FAMILY = "iventas_family"
SUCURSAL_CANON = "TEC_MXL"

OLD_BRANCH_CODE = "tecnologico"
NEW_BRANCH_CODE = "tecnologico-2"


def _read_tecnologico_aliases(connection):
    return (
        connection.execute(
            sa.text(
                """
                SELECT
                    raw_branch_name,
                    sucursal_canon,
                    is_active
                FROM track_branch_aliases
                WHERE source_family = :source_family
                  AND (
                        raw_branch_name IN (
                            :old_branch_code,
                            :new_branch_code
                        )
                        OR sucursal_canon = :sucursal_canon
                  )
                ORDER BY raw_branch_name
                """
            ),
            {
                "source_family": SOURCE_FAMILY,
                "old_branch_code": OLD_BRANCH_CODE,
                "new_branch_code": NEW_BRANCH_CODE,
                "sucursal_canon": SUCURSAL_CANON,
            },
        )
        .mappings()
        .all()
    )


def _assert_state(
    connection,
    *,
    expected_branch_code,
):
    rows = _read_tecnologico_aliases(connection)

    if len(rows) != 1:
        raise RuntimeError(
            "Estado iVentas inesperado para TEC_MXL. "
            f"Se esperaba exactamente 1 alias y hay {len(rows)}."
        )

    row = rows[0]

    if (
        row["raw_branch_name"] != expected_branch_code
        or row["sucursal_canon"] != SUCURSAL_CANON
        or not bool(row["is_active"])
    ):
        raise RuntimeError(
            "Alias iVentas inesperado para TEC_MXL: "
            f"{dict(row)}"
        )


def _replace_branch_code(
    connection,
    *,
    source_branch_code,
    target_branch_code,
):
    result = connection.execute(
        sa.text(
            """
            UPDATE track_branch_aliases
            SET raw_branch_name = :target_branch_code
            WHERE source_family = :source_family
              AND raw_branch_name = :source_branch_code
              AND sucursal_canon = :sucursal_canon
              AND is_active = true
            """
        ),
        {
            "source_family": SOURCE_FAMILY,
            "source_branch_code": source_branch_code,
            "target_branch_code": target_branch_code,
            "sucursal_canon": SUCURSAL_CANON,
        },
    )

    if result.rowcount != 1:
        raise RuntimeError(
            "No se actualizó exactamente un alias "
            f"iVentas para {SUCURSAL_CANON}. "
            f"Filas afectadas={result.rowcount}."
        )


def upgrade():
    connection = op.get_bind()

    _assert_state(
        connection,
        expected_branch_code=OLD_BRANCH_CODE,
    )

    _replace_branch_code(
        connection,
        source_branch_code=OLD_BRANCH_CODE,
        target_branch_code=NEW_BRANCH_CODE,
    )

    _assert_state(
        connection,
        expected_branch_code=NEW_BRANCH_CODE,
    )


def downgrade():
    connection = op.get_bind()

    _assert_state(
        connection,
        expected_branch_code=NEW_BRANCH_CODE,
    )

    _replace_branch_code(
        connection,
        source_branch_code=NEW_BRANCH_CODE,
        target_branch_code=OLD_BRANCH_CODE,
    )

    _assert_state(
        connection,
        expected_branch_code=OLD_BRANCH_CODE,
    )
