"""add cargos recurrentes structured snapshots

Revision ID: 8fc1fb41935d
Revises: a3a33eef229e
Create Date: 2026-04-02 11:52:41.469335

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8fc1fb41935d'
down_revision = 'a3a33eef229e'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cargos_recurrentes_snapshots",
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
            name="fk_cargos_recurrentes_snapshots_warehouse_upload_id",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_cargos_recurrentes_snapshots"),
        sa.UniqueConstraint(
            "warehouse_upload_id",
            name="uq_cargos_recurrentes_snapshots_warehouse_upload_id",
        ),
    )

    op.create_index(
        "ix_cargos_recurrentes_snapshots_business_date",
        "cargos_recurrentes_snapshots",
        ["business_date"],
        unique=False,
    )

    op.create_index(
        "ix_cargos_recurrentes_snapshots_is_canonical",
        "cargos_recurrentes_snapshots",
        ["is_canonical"],
        unique=False,
    )

    op.create_table(
        "cargos_recurrentes_snapshot_rows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("folio", sa.String(length=100), nullable=False),
        sa.Column("id_socio", sa.String(length=100), nullable=False),
        sa.Column("pin", sa.String(length=100), nullable=False),
        sa.Column("nombre", sa.String(length=255), nullable=False),
        sa.Column("sucursal", sa.String(length=255), nullable=False),
        sa.Column("fecha_inicio", sa.String(length=50), nullable=False),
        sa.Column("fecha_proximo_pago", sa.String(length=50), nullable=False),
        sa.Column("numero_intentos", sa.Integer(), nullable=False),
        sa.Column("hd", sa.String(length=100), nullable=True),
        sa.Column("estatus", sa.String(length=100), nullable=False),
        sa.Column("importe", sa.Numeric(12, 2), nullable=False),
        sa.Column("meses_pendiente", sa.String(length=100), nullable=True),
        sa.Column("fecha_fin_contrato", sa.String(length=50), nullable=True),
        sa.Column("tipo_contrato", sa.String(length=100), nullable=True),
        sa.Column("contrato_ajuste", sa.String(length=100), nullable=True),
        sa.Column("acciones", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["cargos_recurrentes_snapshots.id"],
            name="fk_cargos_recurrentes_snapshot_rows_snapshot_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_cargos_recurrentes_snapshot_rows"),
    )

    op.create_index(
        "ix_cargos_recurrentes_snapshot_rows_snapshot_id",
        "cargos_recurrentes_snapshot_rows",
        ["snapshot_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_cargos_recurrentes_snapshot_rows_snapshot_id",
        table_name="cargos_recurrentes_snapshot_rows",
    )

    op.drop_table("cargos_recurrentes_snapshot_rows")

    op.drop_index(
        "ix_cargos_recurrentes_snapshots_is_canonical",
        table_name="cargos_recurrentes_snapshots",
    )

    op.drop_index(
        "ix_cargos_recurrentes_snapshots_business_date",
        table_name="cargos_recurrentes_snapshots",
    )

    op.drop_table("cargos_recurrentes_snapshots")