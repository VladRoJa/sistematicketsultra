"""create reporte_direccion snapshots tables

Revision ID: 385506ff0d5b
Revises: b699b5658ae1
Create Date: 2026-03-22 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "385506ff0d5b"
down_revision = "b699b5658ae1"
branch_labels = None
depends_on = None


SNAPSHOTS_TABLE = "reporte_direccion_snapshots"
ROWS_TABLE = "reporte_direccion_snapshot_rows"


def upgrade():
    op.create_table(
        SNAPSHOTS_TABLE,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("warehouse_upload_id", sa.BigInteger(), nullable=False),
        sa.Column("report_type_key", sa.String(length=64), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot_kind", sa.String(length=32), nullable=False),
        sa.Column(
            "is_canonical",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "row_count_detected",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "row_count_valid",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "row_count_rejected",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_upload_id"],
            ["warehouse_uploads.id"],
            name="fk_reporte_direccion_snapshots_warehouse_upload_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "warehouse_upload_id",
            name="uq_reporte_direccion_snapshots_warehouse_upload_id",
        ),
        sa.CheckConstraint(
            "report_type_key = 'reporte_direccion'",
            name="ck_reporte_direccion_snapshots_report_type_key",
        ),
        sa.CheckConstraint(
            "snapshot_kind IN ('daily', 'month_end_close')",
            name="ck_reporte_direccion_snapshots_snapshot_kind",
        ),
        sa.CheckConstraint(
            "row_count_detected >= 0",
            name="ck_reporte_direccion_snapshots_row_count_detected_nonnegative",
        ),
        sa.CheckConstraint(
            "row_count_valid >= 0",
            name="ck_reporte_direccion_snapshots_row_count_valid_nonnegative",
        ),
        sa.CheckConstraint(
            "row_count_rejected >= 0",
            name="ck_reporte_direccion_snapshots_row_count_rejected_nonnegative",
        ),
        sa.CheckConstraint(
            "row_count_valid + row_count_rejected <= row_count_detected",
            name="ck_reporte_direccion_snapshots_row_counts_consistent",
        ),
    )

    op.create_index(
        "ix_reporte_direccion_snapshots_business_date_captured_at",
        SNAPSHOTS_TABLE,
        ["business_date", "captured_at"],
        unique=False,
    )

    op.create_index(
        "ix_reporte_direccion_snapshots_captured_at",
        SNAPSHOTS_TABLE,
        ["captured_at"],
        unique=False,
    )

    op.create_index(
        "uq_reporte_direccion_snapshots_business_date_canonical",
        SNAPSHOTS_TABLE,
        ["business_date"],
        unique=True,
        postgresql_where=sa.text("is_canonical = true"),
    )

    op.create_table(
        ROWS_TABLE,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("sucursal", sa.String(length=128), nullable=False),
        sa.Column("socios_activos_totales", sa.Integer(), nullable=True),
        sa.Column("socios_activos_kpi", sa.Integer(), nullable=True),
        sa.Column("socios_kpi_m2", sa.Numeric(10, 2), nullable=True),
        sa.Column("asistencia_hoy", sa.Integer(), nullable=True),
        sa.Column("diarios_hoy", sa.Integer(), nullable=True),
        sa.Column("gympass", sa.Integer(), nullable=True),
        sa.Column("totalpass", sa.Integer(), nullable=True),
        sa.Column("pases_cortesia", sa.Integer(), nullable=True),
        sa.Column("ingreso_hoy", sa.Numeric(14, 2), nullable=True),
        sa.Column(
            "ingreso_acumulado_semana_en_curso",
            sa.Numeric(14, 2),
            nullable=True,
        ),
        sa.Column(
            "ingreso_acumulado_mes_en_curso",
            sa.Numeric(14, 2),
            nullable=True,
        ),
        sa.Column(
            "membresia_domiciliada_mes_en_curso",
            sa.Numeric(14, 2),
            nullable=True,
        ),
        sa.Column(
            "pago_posterior_domiciliado_mes_en_curso",
            sa.Numeric(14, 2),
            nullable=True,
        ),
        sa.Column("producto_pct_venta", sa.Numeric(7, 4), nullable=True),
        sa.Column(
            "ingreso_acumulado_mismo_mes_anio_anterior",
            sa.Numeric(14, 2),
            nullable=True,
        ),
        sa.Column("hora_apertura_raw", sa.String(length=32), nullable=True),
        sa.Column("hora_clausura_raw", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            [f"{SNAPSHOTS_TABLE}.id"],
            name="fk_reporte_direccion_snapshot_rows_snapshot_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "snapshot_id",
            "sucursal",
            name="uq_reporte_direccion_snapshot_rows_snapshot_id_sucursal",
        ),
        sa.CheckConstraint(
            "socios_activos_totales IS NULL OR socios_activos_totales >= 0",
            name="ck_rdsr_socios_activos_totales_nonnegative",
        ),
        sa.CheckConstraint(
            "socios_activos_kpi IS NULL OR socios_activos_kpi >= 0",
            name="ck_rdsr_socios_activos_kpi_nonnegative",
        ),
        sa.CheckConstraint(
            "socios_kpi_m2 IS NULL OR socios_kpi_m2 >= 0",
            name="ck_rdsr_socios_kpi_m2_nonnegative",
        ),
        sa.CheckConstraint(
            "asistencia_hoy IS NULL OR asistencia_hoy >= 0",
            name="ck_rdsr_asistencia_hoy_nonnegative",
        ),
        sa.CheckConstraint(
            "diarios_hoy IS NULL OR diarios_hoy >= 0",
            name="ck_rdsr_diarios_hoy_nonnegative",
        ),
        sa.CheckConstraint(
            "gympass IS NULL OR gympass >= 0",
            name="ck_rdsr_gympass_nonnegative",
        ),
        sa.CheckConstraint(
            "totalpass IS NULL OR totalpass >= 0",
            name="ck_rdsr_totalpass_nonnegative",
        ),
        sa.CheckConstraint(
            "pases_cortesia IS NULL OR pases_cortesia >= 0",
            name="ck_rdsr_pases_cortesia_nonnegative",
        ),
    )

    op.create_index(
        "ix_reporte_direccion_snapshot_rows_sucursal",
        ROWS_TABLE,
        ["sucursal"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_reporte_direccion_snapshot_rows_sucursal",
        table_name=ROWS_TABLE,
    )

    op.drop_table(ROWS_TABLE)

    op.drop_index(
        "uq_reporte_direccion_snapshots_business_date_canonical",
        table_name=SNAPSHOTS_TABLE,
        postgresql_where=sa.text("is_canonical = true"),
    )
    op.drop_index(
        "ix_reporte_direccion_snapshots_captured_at",
        table_name=SNAPSHOTS_TABLE,
    )
    op.drop_index(
        "ix_reporte_direccion_snapshots_business_date_captured_at",
        table_name=SNAPSHOTS_TABLE,
    )

    op.drop_table(SNAPSHOTS_TABLE)