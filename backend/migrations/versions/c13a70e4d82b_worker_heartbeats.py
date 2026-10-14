"""M1 worker liveness without changing scheduler execution.

Revision ID: c13a70e4d82b
Revises: f62a1b9d4c07
"""
from alembic import op
import sqlalchemy as sa

revision = "c13a70e4d82b"
down_revision = "f62a1b9d4c07"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "system_worker_heartbeats",
        sa.Column("worker_key", sa.String(64), nullable=False),
        sa.Column("instance_id", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("poll_interval_seconds", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("worker_key", "instance_id",
                                name="pk_system_worker_heartbeats"),
        sa.CheckConstraint("poll_interval_seconds BETWEEN 10 AND 3600",
                           name="ck_system_worker_heartbeat_poll"),
    )
    op.create_index("ix_system_worker_heartbeat_last_seen",
                    "system_worker_heartbeats", ["last_seen_at"])


def downgrade():
    count = op.get_bind().execute(
        sa.text("SELECT count(*) FROM system_worker_heartbeats")
    ).scalar()
    if count:
        raise RuntimeError(
            "La tabla contiene latidos históricos. "
            "No borrar sin respaldo y autorización."
        )
    op.drop_index("ix_system_worker_heartbeat_last_seen",
                  table_name="system_worker_heartbeats")
    op.drop_table("system_worker_heartbeats")
