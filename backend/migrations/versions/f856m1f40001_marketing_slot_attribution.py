"""M1-F4: nullable, per-run Marketing scheduler slot attribution.

Revision ID: f856m1f40001
Revises: f856opcap1013

No backfill: preexisting runs cannot be reliably tied to a slot.
"""
from alembic import op
import sqlalchemy as sa

revision = "f856m1f40001"
down_revision = "f856opcap1013"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("marketing_iventas_sync_runs", "marketing_meta_sync_runs"):
        op.add_column(
            table, sa.Column("scheduler_slot_at", sa.DateTime(timezone=True), nullable=True)
        )
        op.create_index(f"ix_{table}_scheduler_slot_at", table, ["scheduler_slot_at"])


def downgrade():
    for table in ("marketing_meta_sync_runs", "marketing_iventas_sync_runs"):
        op.drop_index(f"ix_{table}_scheduler_slot_at", table_name=table)
        op.drop_column(table, "scheduler_slot_at")
