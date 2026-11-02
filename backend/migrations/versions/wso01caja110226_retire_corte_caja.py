"""WSO-01: retire Corte de Caja structured storage.

Revision ID: wso01caja110226
Revises: v2e4b3103026

WARNING: upgrade irrevocably removes structured Corte de Caja rows.
Only run after the production backup and restore verification gates in
CONTRATO_WAREHOUSE_STORAGE_OPTIMIZATION_V1.md. A downgrade recreates
empty tables: it cannot recover deleted historical rows.
"""

from alembic import op
import sqlalchemy as sa


revision = "wso01caja110226"
down_revision = "v2e4b3103026"
branch_labels = None
depends_on = None


def upgrade():
    # Preserve the tiny report type for historical warehouse_uploads FK lineage,
    # but hide it from active catalogs.
    op.execute(
        "UPDATE public.warehouse_report_types "
        "SET active = FALSE WHERE key = 'corte_caja'"
    )

    # A low lock timeout avoids blocking production queries indefinitely.
    # No CASCADE: fail loudly if new external dependencies were introduced.
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.drop_table("corte_caja_snapshot_rows", schema="public")
    op.drop_table("corte_caja_snapshots", schema="public")


def downgrade():
    # Schema-only reversal; data cannot be reconstructed by Alembic.
    op.create_table(
        "corte_caja_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("warehouse_upload_id", sa.Integer(), nullable=False),
        sa.Column("report_type_key", sa.String(length=100), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot_kind", sa.String(length=50), nullable=False),
        sa.Column(
            "is_canonical", sa.Boolean(), nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("row_count_detected", sa.Integer(), nullable=False),
        sa.Column("row_count_valid", sa.Integer(), nullable=False),
        sa.Column(
            "row_count_rejected", sa.Integer(), nullable=False,
            server_default="0",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["warehouse_upload_id"],
            ["public.warehouse_uploads.id"],
            name="fk_corte_caja_snapshots_warehouse_upload_id",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_corte_caja_snapshots"),
        sa.UniqueConstraint(
            "warehouse_upload_id",
            name="uq_corte_caja_snapshots_warehouse_upload_id",
        ),
        schema="public",
    )
    op.create_index(
        "ix_corte_caja_snapshots_business_date",
        "corte_caja_snapshots", ["business_date"],
        unique=False, schema="public",
    )
    op.create_index(
        "ix_corte_caja_snapshots_is_canonical",
        "corte_caja_snapshots", ["is_canonical"],
        unique=False, schema="public",
    )

    op.create_table(
        "corte_caja_snapshot_rows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("clave", sa.String(length=100), nullable=True),
        sa.Column("folio", sa.String(length=100), nullable=False),
        sa.Column("hora", sa.String(length=20), nullable=False),
        sa.Column("nombre", sa.String(length=255), nullable=False),
        sa.Column("importe", sa.Numeric(12, 2), nullable=False),
        sa.Column("pago", sa.String(length=50), nullable=True),
        sa.Column("renovacion", sa.String(length=50), nullable=True),
        sa.Column("operacion", sa.String(length=100), nullable=True),
        sa.Column("tipo_pago", sa.String(length=100), nullable=True),
        sa.Column("recepcion", sa.String(length=255), nullable=True),
        sa.Column("sucursal", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["public.corte_caja_snapshots.id"],
            name="fk_corte_caja_snapshot_rows_snapshot_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_corte_caja_snapshot_rows"),
        schema="public",
    )
    op.create_index(
        "ix_corte_caja_snapshot_rows_snapshot_id",
        "corte_caja_snapshot_rows", ["snapshot_id"],
        unique=False, schema="public",
    )

    op.execute(
        "UPDATE public.warehouse_report_types "
        "SET active = TRUE WHERE key = 'corte_caja'"
    )
