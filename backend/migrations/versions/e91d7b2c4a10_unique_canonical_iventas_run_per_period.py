"""unique canonical iventas run per period

Revision ID: e91d7b2c4a10
Revises: c42e918f6a31
Create Date: 2026-08-10
"""

from alembic import op
import sqlalchemy as sa


revision = "e91d7b2c4a10"
down_revision = "c42e918f6a31"
branch_labels = None
depends_on = None


INDEX_NAME = (
    "uq_marketing_iventas_sync_runs_"
    "canonical_period"
)

TABLE_NAME = "marketing_iventas_sync_runs"


def upgrade():
    op.create_index(
        INDEX_NAME,
        TABLE_NAME,
        ["period_key"],
        unique=True,
        postgresql_where=sa.text(
            "is_canonical = true"
        ),
    )


def downgrade():
    op.drop_index(
        INDEX_NAME,
        table_name=TABLE_NAME,
    )
