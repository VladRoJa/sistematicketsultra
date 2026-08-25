"""add socios vencidos edad quality fields

Revision ID: aab1ed1a5e31
Revises: b83203045cc7
Create Date: 2026-08-24
"""

from alembic import op
import sqlalchemy as sa


revision = "aab1ed1a5e31"
down_revision = "b83203045cc7"
branch_labels = None
depends_on = None


EDAD_QUALITY_CHECK = (
    "(edad_status = 'VALID' "
    "AND edad_raw BETWEEN 0 AND 120 "
    "AND edad = edad_raw) "
    "OR (edad_status = 'INVALID_OUT_OF_RANGE' "
    "AND edad_raw IS NOT NULL "
    "AND (edad_raw < 0 OR edad_raw > 120) "
    "AND edad IS NULL) "
    "OR (edad_status = 'MISSING' "
    "AND edad_raw IS NULL "
    "AND edad IS NULL)"
)


def upgrade():
    op.add_column(
        "socios_vencidos_snapshot_rows",
        sa.Column("edad_raw", sa.Integer(), nullable=True),
    )
    op.add_column(
        "socios_vencidos_snapshot_rows",
        sa.Column("edad_status", sa.String(length=32), nullable=True),
    )

    op.execute(
        """
        UPDATE socios_vencidos_snapshot_rows
        SET
            edad_raw = edad,
            edad_status = CASE
                WHEN edad IS NULL THEN 'MISSING'
                WHEN edad BETWEEN 0 AND 120 THEN 'VALID'
                ELSE 'INVALID_OUT_OF_RANGE'
            END,
            edad = CASE
                WHEN edad BETWEEN 0 AND 120 THEN edad
                ELSE NULL
            END
        """
    )

    op.alter_column(
        "socios_vencidos_snapshot_rows",
        "edad_status",
        existing_type=sa.String(length=32),
        nullable=False,
    )
    op.create_check_constraint(
        "ck_socios_vencidos_rows_edad_quality",
        "socios_vencidos_snapshot_rows",
        EDAD_QUALITY_CHECK,
    )


def downgrade():
    op.drop_constraint(
        "ck_socios_vencidos_rows_edad_quality",
        "socios_vencidos_snapshot_rows",
        type_="check",
    )
    op.drop_column(
        "socios_vencidos_snapshot_rows",
        "edad_status",
    )
    op.drop_column(
        "socios_vencidos_snapshot_rows",
        "edad_raw",
    )
