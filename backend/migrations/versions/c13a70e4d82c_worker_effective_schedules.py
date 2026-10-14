"""M1-C typed effective schedule snapshots per worker instance.

Revision ID: c13a70e4d82c
Revises: c13a70e4d82b
"""
from alembic import op
import sqlalchemy as sa

revision = "c13a70e4d82c"
down_revision = "c13a70e4d82b"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "system_worker_heartbeats",
        sa.Column("job_schedules", sa.JSON(), nullable=True),
    )


def downgrade():
    op.drop_column("system_worker_heartbeats", "job_schedules")
