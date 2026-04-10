"""create domiciliados_total_snapshots

Revision ID: 2f1b9a227af9
Revises: cff7b2be472f
Create Date: 2026-04-10 07:00:45.333739

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2f1b9a227af9'
down_revision = 'cff7b2be472f'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "domiciliados_total_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("warehouse_upload_id", sa.BigInteger(), nullable=False),
        sa.Column("report_type_key", sa.Text(), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot_kind", sa.Text(), nullable=False),
        sa.Column("is_canonical", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("row_count_detected", sa.Integer(), nullable=False),
        sa.Column("row_count_valid", sa.Integer(), nullable=False),
        sa.Column("row_count_rejected", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )

    op.create_index(
        "uq_domiciliados_total_snapshots_warehouse_upload_id",
        "domiciliados_total_snapshots",
        ["warehouse_upload_id"],
        unique=True,
    )


def downgrade():
    op.drop_index(
        "uq_domiciliados_total_snapshots_warehouse_upload_id",
        table_name="domiciliados_total_snapshots",
    )
    op.drop_table("domiciliados_total_snapshots")