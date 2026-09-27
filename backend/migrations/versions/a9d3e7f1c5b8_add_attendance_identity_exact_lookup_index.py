"""add attendance identity exact lookup index

Revision ID: a9d3e7f1c5b8
Revises: f4b8c2d6e1a9
Create Date: 2026-09-27
"""

from alembic import op


revision = "a9d3e7f1c5b8"
down_revision = "f4b8c2d6e1a9"
branch_labels = None
depends_on = None


INDEX_NAME = (
    "ix_socios_activos_rows_pin_ingreso_date_snapshot"
)
TABLE_NAME = "socios_activos_snapshot_rows"


def upgrade():
    with op.get_context().autocommit_block():
        op.execute(
            f"""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME}
            ON {TABLE_NAME}
            (
                pin,
                (fecha_ingreso_local::date),
                snapshot_id
            )
            """
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.execute(
            f"""
            DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME}
            """
        )
