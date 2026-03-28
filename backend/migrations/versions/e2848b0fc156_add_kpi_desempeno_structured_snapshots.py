"""add kpi desempeno structured snapshots

Revision ID: e2848b0fc156
Revises: 385506ff0d5b
Create Date: 2026-03-27 11:44:51.478902

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e2848b0fc156'
down_revision = '385506ff0d5b'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "kpi_desempeno_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("warehouse_upload_id", sa.Integer(), nullable=False),
        sa.Column("report_type_key", sa.String(length=100), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot_kind", sa.String(length=50), nullable=False),
        sa.Column("is_canonical", sa.Boolean(), nullable=False),
        sa.Column("row_count_detected", sa.Integer(), nullable=False),
        sa.Column("row_count_valid", sa.Integer(), nullable=False),
        sa.Column("row_count_rejected", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["warehouse_upload_id"],
            ["warehouse_uploads.id"],
            name="fk_kpi_desempeno_snapshots_warehouse_upload_id",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_kpi_desempeno_snapshots"),
        sa.UniqueConstraint(
            "warehouse_upload_id",
            name="uq_kpi_desempeno_snapshots_warehouse_upload_id",
        ),
    )
    op.create_index(
        "ix_kpi_desempeno_snapshots_business_date",
        "kpi_desempeno_snapshots",
        ["business_date"],
        unique=False,
    )
    op.create_index(
        "ix_kpi_desempeno_snapshots_is_canonical",
        "kpi_desempeno_snapshots",
        ["is_canonical"],
        unique=False,
    )

    op.create_table(
        "kpi_desempeno_snapshot_rows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("sucursal", sa.String(length=255), nullable=False),
        sa.Column("socios_activos_inicio_mes", sa.Integer(), nullable=False),
        sa.Column("clientes_nuevo_real", sa.Integer(), nullable=False),
        sa.Column("reactivaciones", sa.Integer(), nullable=False),
        sa.Column("renovaciones", sa.Integer(), nullable=False),
        sa.Column("bajas", sa.Integer(), nullable=False),
        sa.Column("socios_activos_del_mes", sa.Integer(), nullable=False),
        sa.Column("meta_socios_activos_del_mes", sa.Integer(), nullable=False),
        sa.Column("alcance_meta", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["kpi_desempeno_snapshots.id"],
            name="fk_kpi_desempeno_snapshot_rows_snapshot_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_kpi_desempeno_snapshot_rows"),
        sa.UniqueConstraint(
            "snapshot_id",
            "sucursal",
            name="uq_kpi_desempeno_snapshot_rows_snapshot_id_sucursal",
        ),
    )
    op.create_index(
        "ix_kpi_desempeno_snapshot_rows_snapshot_id",
        "kpi_desempeno_snapshot_rows",
        ["snapshot_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_kpi_desempeno_snapshot_rows_snapshot_id",
        table_name="kpi_desempeno_snapshot_rows",
    )
    op.drop_table("kpi_desempeno_snapshot_rows")

    op.drop_index(
        "ix_kpi_desempeno_snapshots_is_canonical",
        table_name="kpi_desempeno_snapshots",
    )
    op.drop_index(
        "ix_kpi_desempeno_snapshots_business_date",
        table_name="kpi_desempeno_snapshots",
    )
    op.drop_table("kpi_desempeno_snapshots")