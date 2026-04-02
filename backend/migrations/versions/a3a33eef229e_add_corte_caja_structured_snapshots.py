"""add corte caja structured snapshots

Revision ID: a3a33eef229e
Revises: 2aea7c0090a8
Create Date: 2026-03-30 10:35:34.084809

"""
from alembic import op
import sqlalchemy as sa


# Reemplaza SOLO esta línea con la revision que te generó Alembic
revision = "a3a33eef229e"
down_revision = "2aea7c0090a8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "corte_caja_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("warehouse_upload_id", sa.Integer(), nullable=False),
        sa.Column("report_type_key", sa.String(length=100), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot_kind", sa.String(length=50), nullable=False),
        sa.Column("is_canonical", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("row_count_detected", sa.Integer(), nullable=False),
        sa.Column("row_count_valid", sa.Integer(), nullable=False),
        sa.Column("row_count_rejected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["warehouse_upload_id"],
            ["warehouse_uploads.id"],
            name="fk_corte_caja_snapshots_warehouse_upload_id",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_corte_caja_snapshots"),
        sa.UniqueConstraint(
            "warehouse_upload_id",
            name="uq_corte_caja_snapshots_warehouse_upload_id",
        ),
    )

    op.create_index(
        "ix_corte_caja_snapshots_business_date",
        "corte_caja_snapshots",
        ["business_date"],
        unique=False,
    )

    op.create_index(
        "ix_corte_caja_snapshots_is_canonical",
        "corte_caja_snapshots",
        ["is_canonical"],
        unique=False,
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
            ["snapshot_id"],
            ["corte_caja_snapshots.id"],
            name="fk_corte_caja_snapshot_rows_snapshot_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_corte_caja_snapshot_rows"),
    )

    op.create_index(
        "ix_corte_caja_snapshot_rows_snapshot_id",
        "corte_caja_snapshot_rows",
        ["snapshot_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_corte_caja_snapshot_rows_snapshot_id",
        table_name="corte_caja_snapshot_rows",
    )

    op.drop_table("corte_caja_snapshot_rows")

    op.drop_index(
        "ix_corte_caja_snapshots_is_canonical",
        table_name="corte_caja_snapshots",
    )

    op.drop_index(
        "ix_corte_caja_snapshots_business_date",
        table_name="corte_caja_snapshots",
    )

    op.drop_table("corte_caja_snapshots")