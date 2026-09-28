"""add socios activos snapshot pin branch index

Revision ID: c7d2e5f8a1b4
Revises: b6c1d9e4f2a7
Create Date: 2026-09-28
"""

from alembic import op


revision = "c7d2e5f8a1b4"
down_revision = "b6c1d9e4f2a7"
branch_labels = None
depends_on = None


INDEX_NAME = (
    "ix_socios_activos_rows_snapshot_pin_branch"
)
TABLE_NAME = "socios_activos_snapshot_rows"


def upgrade():
    with op.get_context().autocommit_block():
        op.execute(
            f"""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME}
            ON {TABLE_NAME}
            (
                snapshot_id,
                pin,
                sucursal_raw
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
