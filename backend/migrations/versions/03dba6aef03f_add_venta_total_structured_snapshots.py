"""add venta total structured snapshots

Revision ID: 03dba6aef03f
Revises: 8fc1fb41935d
Create Date: 2026-04-04 18:33:45.648552

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '03dba6aef03f'
down_revision = '8fc1fb41935d'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "venta_total_snapshots",
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
            name="fk_venta_total_snapshots_warehouse_upload_id",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_venta_total_snapshots"),
        sa.UniqueConstraint(
            "warehouse_upload_id",
            name="uq_venta_total_snapshots_warehouse_upload_id",
        ),
    )

    op.create_index(
        "ix_venta_total_snapshots_business_date",
        "venta_total_snapshots",
        ["business_date"],
        unique=False,
    )

    op.create_index(
        "ix_venta_total_snapshots_is_canonical",
        "venta_total_snapshots",
        ["is_canonical"],
        unique=False,
    )

    op.create_table(
        "venta_total_snapshot_rows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("fecha", sa.String(length=50), nullable=False),
        sa.Column("sucursal", sa.String(length=255), nullable=False),
        sa.Column("folio", sa.String(length=100), nullable=False),
        sa.Column("clave", sa.String(length=100), nullable=True),
        sa.Column("clave_producto", sa.String(length=100), nullable=True),
        sa.Column("descripcion", sa.String(length=255), nullable=False),
        sa.Column("cantidad", sa.Numeric(12, 2), nullable=False),
        sa.Column("precio_unitario", sa.Numeric(12, 2), nullable=False),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False),
        sa.Column("iva_importe", sa.Numeric(12, 2), nullable=False),
        sa.Column("iva_tasa", sa.Numeric(12, 2), nullable=False),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("forma_pago", sa.String(length=100), nullable=False),
        sa.Column("estatus", sa.String(length=100), nullable=False),
        sa.Column("motivo", sa.String(length=255), nullable=True),
        sa.Column("realizo_venta", sa.String(length=255), nullable=False),
        sa.Column("hora", sa.String(length=50), nullable=False),
        sa.Column("id_orden", sa.String(length=100), nullable=True),
        sa.Column("encuesta", sa.String(length=255), nullable=True),
        sa.Column("capturista", sa.String(length=255), nullable=True),
        sa.Column("pin", sa.String(length=100), nullable=True),
        sa.Column("socio", sa.String(length=255), nullable=True),
        sa.Column("nuevo", sa.String(length=100), nullable=True),
        sa.Column("tipo", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["venta_total_snapshots.id"],
            name="fk_venta_total_snapshot_rows_snapshot_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_venta_total_snapshot_rows"),
    )

    op.create_index(
        "ix_venta_total_snapshot_rows_snapshot_id",
        "venta_total_snapshot_rows",
        ["snapshot_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_venta_total_snapshot_rows_snapshot_id",
        table_name="venta_total_snapshot_rows",
    )

    op.drop_table("venta_total_snapshot_rows")

    op.drop_index(
        "ix_venta_total_snapshots_is_canonical",
        table_name="venta_total_snapshots",
    )

    op.drop_index(
        "ix_venta_total_snapshots_business_date",
        table_name="venta_total_snapshots",
    )

    op.drop_table("venta_total_snapshots")
