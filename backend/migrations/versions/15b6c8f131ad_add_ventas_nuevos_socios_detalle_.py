"""add ventas nuevos socios detalle structured snapshots

Revision ID: 15b6c8f131ad
Revises: fbe0895c08c7
Create Date: 2026-07-27 12:14:20.553694
"""

from alembic import op
import sqlalchemy as sa


revision = "15b6c8f131ad"
down_revision = "fbe0895c08c7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ventas_nuevos_socios_detalle_snapshots",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "warehouse_upload_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "report_type_key",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "business_date",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "date_from",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "date_to",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "snapshot_kind",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "is_canonical",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "row_count_detected",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "row_count_valid",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "row_count_rejected",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "metadata_json",
            sa.JSON(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "business_date = date_to",
            name="ck_vns_detalle_snapshots_business_date",
        ),
        sa.CheckConstraint(
            "date_from <= date_to",
            name="ck_vns_detalle_snapshots_valid_date_range",
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_upload_id"],
            ["warehouse_uploads.id"],
            name="fk_vns_detalle_snapshots_warehouse_upload",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_vns_detalle_snapshots",
        ),
        sa.UniqueConstraint(
            "warehouse_upload_id",
            name="uq_vns_detalle_snapshots_warehouse_upload",
        ),
    )

    op.create_index(
        "ix_vns_detalle_snapshots_business_date",
        "ventas_nuevos_socios_detalle_snapshots",
        ["business_date"],
        unique=False,
    )

    op.create_index(
        "ix_vns_detalle_snapshots_date_range",
        "ventas_nuevos_socios_detalle_snapshots",
        ["date_from", "date_to"],
        unique=False,
    )

    op.create_index(
        "ix_vns_detalle_snapshots_is_canonical",
        "ventas_nuevos_socios_detalle_snapshots",
        ["is_canonical"],
        unique=False,
    )

    op.create_table(
        "ventas_nuevos_socios_detalle_snapshot_rows",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "snapshot_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "row_index",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "row_hash",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "id_socio",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "pin",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column(
            "sucursal_raw",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "sucursal_id",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "nombre",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "apellido_paterno",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "apellido_materno",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "lada",
            sa.String(length=20),
            nullable=False,
        ),
        sa.Column(
            "telefono",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "domicilio",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "genero",
            sa.String(length=50),
            nullable=True,
        ),
        sa.Column(
            "fecha_nacimiento",
            sa.Date(),
            nullable=True,
        ),
        sa.Column(
            "email",
            sa.String(length=320),
            nullable=True,
        ),
        sa.Column(
            "fecha_creacion_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "inscripcion",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "tipo_membresia",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "tarifa",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "total",
            sa.Numeric(precision=14, scale=2),
            nullable=True,
        ),
        sa.Column(
            "fecha_pago_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "fecha_renovacion_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "fecha_firma_contrato_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "tipo_pago_code",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "tipo_tarjeta_code",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "lugar_pago",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "id_folio",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "pase",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "anfitrion",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "total_pagado",
            sa.Numeric(precision=14, scale=2),
            nullable=True,
        ),
        sa.Column(
            "quality_flags",
            sa.JSON(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["ventas_nuevos_socios_detalle_snapshots.id"],
            name="fk_vns_detalle_rows_snapshot",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sucursal_id"],
            ["sucursales.sucursal_id"],
            name="fk_vns_detalle_rows_sucursal",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_vns_detalle_rows",
        ),
        sa.UniqueConstraint(
            "snapshot_id",
            "id_socio",
            name="uq_vns_detalle_rows_snapshot_socio",
        ),
    )

    op.create_index(
        "ix_vns_detalle_rows_snapshot_id",
        "ventas_nuevos_socios_detalle_snapshot_rows",
        ["snapshot_id"],
        unique=False,
    )

    op.create_index(
        "ix_vns_detalle_rows_id_socio",
        "ventas_nuevos_socios_detalle_snapshot_rows",
        ["id_socio"],
        unique=False,
    )

    op.create_index(
        "ix_vns_detalle_rows_snapshot_branch",
        "ventas_nuevos_socios_detalle_snapshot_rows",
        ["snapshot_id", "sucursal_id"],
        unique=False,
    )

    op.create_index(
        "ix_vns_detalle_rows_snapshot_payment",
        "ventas_nuevos_socios_detalle_snapshot_rows",
        ["snapshot_id", "fecha_pago_at"],
        unique=False,
    )

    op.create_index(
        "ix_vns_detalle_rows_telefono",
        "ventas_nuevos_socios_detalle_snapshot_rows",
        ["telefono"],
        unique=False,
    )

    op.create_index(
        "ix_vns_detalle_rows_id_folio",
        "ventas_nuevos_socios_detalle_snapshot_rows",
        ["id_folio"],
        unique=False,
    )

    op.create_index(
        "ix_vns_detalle_rows_tarifa",
        "ventas_nuevos_socios_detalle_snapshot_rows",
        ["tarifa"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_vns_detalle_rows_tarifa",
        table_name="ventas_nuevos_socios_detalle_snapshot_rows",
    )

    op.drop_index(
        "ix_vns_detalle_rows_id_folio",
        table_name="ventas_nuevos_socios_detalle_snapshot_rows",
    )

    op.drop_index(
        "ix_vns_detalle_rows_telefono",
        table_name="ventas_nuevos_socios_detalle_snapshot_rows",
    )

    op.drop_index(
        "ix_vns_detalle_rows_snapshot_payment",
        table_name="ventas_nuevos_socios_detalle_snapshot_rows",
    )

    op.drop_index(
        "ix_vns_detalle_rows_snapshot_branch",
        table_name="ventas_nuevos_socios_detalle_snapshot_rows",
    )

    op.drop_index(
        "ix_vns_detalle_rows_id_socio",
        table_name="ventas_nuevos_socios_detalle_snapshot_rows",
    )

    op.drop_index(
        "ix_vns_detalle_rows_snapshot_id",
        table_name="ventas_nuevos_socios_detalle_snapshot_rows",
    )

    op.drop_table(
        "ventas_nuevos_socios_detalle_snapshot_rows"
    )

    op.drop_index(
        "ix_vns_detalle_snapshots_is_canonical",
        table_name="ventas_nuevos_socios_detalle_snapshots",
    )

    op.drop_index(
        "ix_vns_detalle_snapshots_date_range",
        table_name="ventas_nuevos_socios_detalle_snapshots",
    )

    op.drop_index(
        "ix_vns_detalle_snapshots_business_date",
        table_name="ventas_nuevos_socios_detalle_snapshots",
    )

    op.drop_table(
        "ventas_nuevos_socios_detalle_snapshots"
    )
