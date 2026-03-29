"""add kpi ventas nuevos socios structured snapshots

Revision ID: 2aea7c0090a8
Revises: e2848b0fc156
Create Date: 2026-03-27 18:59:50.314428

"""
from alembic import op
import sqlalchemy as sa


# Reemplaza SOLO esta línea con la revision que te generó Alembic
revision = "2aea7c0090a8"
down_revision = "e2848b0fc156"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "kpi_ventas_nuevos_socios_snapshots",
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
            name="fk_kpi_ventas_nuevos_socios_snapshots_warehouse_upload_id",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_kpi_ventas_nuevos_socios_snapshots"),
        sa.UniqueConstraint(
            "warehouse_upload_id",
            name="uq_kpi_ventas_nuevos_socios_snapshots_warehouse_upload_id",
        ),
    )

    op.create_index(
        "ix_kpi_ventas_nuevos_socios_snapshots_business_date",
        "kpi_ventas_nuevos_socios_snapshots",
        ["business_date"],
        unique=False,
    )

    op.create_index(
        "ix_kpi_ventas_nuevos_socios_snapshots_is_canonical",
        "kpi_ventas_nuevos_socios_snapshots",
        ["is_canonical"],
        unique=False,
    )

    op.create_table(
        "kpi_ventas_nuevos_socios_snapshot_rows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("sucursal", sa.String(length=255), nullable=False),
        sa.Column("numero_cnm_meta", sa.Integer(), nullable=False),
        sa.Column("ingreso_por_cnm_meta", sa.Numeric(12, 2), nullable=False),
        sa.Column("clientes_nuevos_real", sa.Integer(), nullable=False),
        sa.Column("ingreso_clientes_nuevos_real", sa.Numeric(12, 2), nullable=False),
        sa.Column("cnreal_menos_meta_cnm", sa.Integer(), nullable=False),
        sa.Column("porcentaje_meta", sa.Numeric(12, 2), nullable=False),
        sa.Column("cnreal_menos_meta_cnm_alt", sa.Numeric(12, 2), nullable=False),
        sa.Column("porcentaje_meta_alt", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["kpi_ventas_nuevos_socios_snapshots.id"],
            name="fk_kpi_ventas_nuevos_socios_snapshot_rows_snapshot_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_kpi_ventas_nuevos_socios_snapshot_rows"),
        sa.UniqueConstraint(
            "snapshot_id",
            "sucursal",
            name="uq_kpi_ventas_nuevos_socios_snapshot_rows_snapshot_id_sucursal",
        ),
    )

    op.create_index(
        "ix_kpi_ventas_nuevos_socios_snapshot_rows_snapshot_id",
        "kpi_ventas_nuevos_socios_snapshot_rows",
        ["snapshot_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_kpi_ventas_nuevos_socios_snapshot_rows_snapshot_id",
        table_name="kpi_ventas_nuevos_socios_snapshot_rows",
    )

    op.drop_table("kpi_ventas_nuevos_socios_snapshot_rows")

    op.drop_index(
        "ix_kpi_ventas_nuevos_socios_snapshots_is_canonical",
        table_name="kpi_ventas_nuevos_socios_snapshots",
    )

    op.drop_index(
        "ix_kpi_ventas_nuevos_socios_snapshots_business_date",
        table_name="kpi_ventas_nuevos_socios_snapshots",
    )

    op.drop_table("kpi_ventas_nuevos_socios_snapshots")