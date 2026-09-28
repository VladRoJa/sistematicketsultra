"""add attendance historical visit lookup index

Revision ID: b6c1d9e4f2a7
Revises: a9d3e7f1c5b8
Create Date: 2026-09-28
"""

from alembic import op


revision = "b6c1d9e4f2a7"
down_revision = "a9d3e7f1c5b8"
branch_labels = None
depends_on = None


INDEX_NAME = (
    "ix_wh_attendance_visits_member_identity_history"
)
TABLE_NAME = "warehouse_attendance_visits"


def upgrade():
    with op.get_context().autocommit_block():
        op.execute(
            f"""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME}
            ON {TABLE_NAME}
            (
                member_pin,
                member_since,
                business_date
            )
            WHERE attendance_type = 'SOCIO'
            """
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.execute(
            f"""
            DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME}
            """
        )
