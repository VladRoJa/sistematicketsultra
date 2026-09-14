"""Add composite indexes for reactivation active-member lookups.

Revision ID: a2d5f8c1b3e7
Revises: f4a1c8d2e6b7
Create Date: 2026-09-14
"""

from alembic import op


revision = "a2d5f8c1b3e7"
down_revision = "f4a1c8d2e6b7"
branch_labels = None
depends_on = None


PIN_INDEX = "ix_socios_activos_rows_snapshot_pin"
PHONE_INDEX = "ix_socios_activos_rows_snapshot_phone"
TABLE_NAME = "socios_activos_snapshot_rows"


def _create_index_concurrently(name: str, columns_sql: str) -> None:
    with op.get_context().autocommit_block():
        op.execute(
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} "
            f"ON {TABLE_NAME} ({columns_sql})"
        )


def _drop_index_concurrently(name: str) -> None:
    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")


def upgrade():
    _create_index_concurrently(PIN_INDEX, "snapshot_id, pin")
    _create_index_concurrently(PHONE_INDEX, "snapshot_id, telefono_digits")


def downgrade():
    _drop_index_concurrently(PHONE_INDEX)
    _drop_index_concurrently(PIN_INDEX)
