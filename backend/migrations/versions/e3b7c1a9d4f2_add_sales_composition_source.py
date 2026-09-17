"""add sales composition source

Revision ID: e3b7c1a9d4f2
Revises: c8f1d4a7e2b9
Create Date: 2026-09-17
"""

from alembic import op
import sqlalchemy as sa


revision = "e3b7c1a9d4f2"
down_revision = "c8f1d4a7e2b9"
branch_labels = None
depends_on = None


def _get_id(bind, table_name: str, key: str) -> int:
    return bind.execute(
        sa.text(f"SELECT id FROM {table_name} WHERE key = :key"),
        {"key": key},
    ).scalar_one()


def upgrade():
    bind = op.get_bind()
    family_id = _get_id(
        bind,
        "warehouse_families",
        "reportes_transaccionales",
    )
    source_id = _get_id(bind, "warehouse_sources", "gasca")
    role_id = _get_id(
        bind,
        "warehouse_operational_roles",
        "FUENTE_PRINCIPAL",
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO warehouse_report_types (
                key, label, family_id, default_source_id,
                default_operational_role_id, default_period_type, active
            )
            SELECT
                'resumen_ventas', 'Resumen Ventas / Composición', :family_id,
                :source_id, :role_id, 'rango', true
            WHERE NOT EXISTS (
                SELECT 1 FROM warehouse_report_types
                WHERE key = 'resumen_ventas'
            )
            """
        ),
        {
            "family_id": family_id,
            "source_id": source_id,
            "role_id": role_id,
        },
    )

    op.create_table(
        "sales_composition_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("warehouse_upload_id", sa.Integer(), nullable=False),
        sa.Column("report_type_key", sa.String(length=80), nullable=False),
        sa.Column("date_from", sa.Date(), nullable=False),
        sa.Column("date_to", sa.Date(), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "is_canonical",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("current_label", sa.String(length=120), nullable=False),
        sa.Column("comparison_label", sa.String(length=120), nullable=False),
        sa.Column("row_count_detected", sa.Integer(), nullable=False),
        sa.Column("row_count_valid", sa.Integer(), nullable=False),
        sa.Column(
            "row_count_rejected",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("summary_totals", sa.JSON(), nullable=False),
        sa.Column("data_quality", sa.JSON(), nullable=False),
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
            name="fk_sales_comp_snapshot_upload",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_sales_composition_snapshots",
        ),
        sa.UniqueConstraint(
            "warehouse_upload_id",
            name="uq_sales_comp_snapshot_upload",
        ),
    )
    op.create_index(
        "ix_sales_comp_snapshots_business_date",
        "sales_composition_snapshots",
        ["business_date"],
        unique=False,
    )
    op.create_index(
        "ix_sales_comp_snapshots_canonical",
        "sales_composition_snapshots",
        ["is_canonical", "business_date"],
        unique=False,
    )

    op.create_table(
        "sales_composition_rows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("source_sheet", sa.String(length=80), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("row_kind", sa.String(length=20), nullable=False),
        sa.Column("tariff_row_index", sa.Integer(), nullable=False),
        sa.Column("sales_mode", sa.String(length=20), nullable=False),
        sa.Column("family", sa.String(length=120), nullable=True),
        sa.Column("contract_type", sa.String(length=120), nullable=True),
        sa.Column("plan_type", sa.String(length=80), nullable=True),
        sa.Column("tariff_name", sa.String(length=255), nullable=False),
        sa.Column("source_cost", sa.Numeric(18, 2), nullable=True),
        sa.Column("monthly_equivalent", sa.Numeric(18, 2), nullable=True),
        sa.Column("free_months_raw", sa.String(length=80), nullable=True),
        sa.Column("branch_raw", sa.String(length=255), nullable=True),
        sa.Column("current_quantity", sa.Numeric(18, 2), nullable=False),
        sa.Column("current_flow", sa.Numeric(18, 2), nullable=False),
        sa.Column("comparison_quantity", sa.Numeric(18, 2), nullable=False),
        sa.Column("comparison_flow", sa.Numeric(18, 2), nullable=False),
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
            ["sales_composition_snapshots.id"],
            name="fk_sales_comp_row_snapshot",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sales_composition_rows"),
        sa.UniqueConstraint(
            "snapshot_id",
            "row_index",
            name="uq_sales_composition_rows_snapshot_row",
        ),
    )
    op.create_index(
        "ix_sales_comp_rows_snapshot_kind",
        "sales_composition_rows",
        ["snapshot_id", "row_kind"],
        unique=False,
    )
    op.create_index(
        "ix_sales_comp_rows_snapshot_mode",
        "sales_composition_rows",
        ["snapshot_id", "sales_mode"],
        unique=False,
    )
    op.create_index(
        "ix_sales_comp_rows_snapshot_branch",
        "sales_composition_rows",
        ["snapshot_id", "branch_raw"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_sales_comp_rows_snapshot_branch",
        table_name="sales_composition_rows",
    )
    op.drop_index(
        "ix_sales_comp_rows_snapshot_mode",
        table_name="sales_composition_rows",
    )
    op.drop_index(
        "ix_sales_comp_rows_snapshot_kind",
        table_name="sales_composition_rows",
    )
    op.drop_table("sales_composition_rows")
    op.drop_index(
        "ix_sales_comp_snapshots_canonical",
        table_name="sales_composition_snapshots",
    )
    op.drop_index(
        "ix_sales_comp_snapshots_business_date",
        table_name="sales_composition_snapshots",
    )
    op.drop_table("sales_composition_snapshots")
    op.execute(
        "DELETE FROM warehouse_report_types WHERE key = 'resumen_ventas'"
    )
