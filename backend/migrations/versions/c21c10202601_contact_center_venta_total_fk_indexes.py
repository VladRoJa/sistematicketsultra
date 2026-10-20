"""Index Contact Center evidence FKs for safe Venta Total retention.

Revision ID: c21c10202601
Revises: b20c10202601
Create Date: 2026-10-20

Child-side PostgreSQL FK columns are not indexed automatically.
Retention deletes thousands of snapshot rows, causing FK ON DELETE SET NULL
triggers to scan Contact Center unless these indexes are available.

Indexes are partial because NULL is never a matching FK reference.
CREATE INDEX CONCURRENTLY keeps Contact Center writes available during build.
"""
from alembic import op
import sqlalchemy as sa

revision = "c21c10202601"
down_revision = "b20c10202601"
branch_labels = None
depends_on = None

_INDEXES = (
    ("ix_cc_appointments_vt_snapshot_id",
     "contact_center_appointments", "venta_total_snapshot_id"),
    ("ix_cc_appointments_vt_snapshot_row_id",
     "contact_center_appointments", "venta_total_snapshot_row_id"),
    ("ix_cc_result_events_vt_snapshot_id",
     "contact_center_appointment_result_events", "venta_total_snapshot_id"),
    ("ix_cc_result_events_vt_snapshot_row_id",
     "contact_center_appointment_result_events", "venta_total_snapshot_row_id"),
)


def upgrade():
    # PostgreSQL CREATE INDEX CONCURRENTLY cannot run inside a transaction.
    # Alembic commits any preceding migration transaction before this block.
    with op.get_context().autocommit_block():
        for name, table, column in _INDEXES:
            op.create_index(
                name,
                table,
                [column],
                unique=False,
                postgresql_where=sa.text(f"{column} IS NOT NULL"),
                postgresql_concurrently=True,
            )


def downgrade():
    with op.get_context().autocommit_block():
        for name, table, _column in reversed(_INDEXES):
            op.drop_index(
                name,
                table_name=table,
                postgresql_concurrently=True,
            )
