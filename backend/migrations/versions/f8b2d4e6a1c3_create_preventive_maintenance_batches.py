"""create preventive maintenance batches and items

Revision ID: f8b2d4e6a1c3
Revises: e7a1c3d9f2b4
Create Date: 2026-09-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f8b2d4e6a1c3"
down_revision = "e7a1c3d9f2b4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "maintenance_preventive_batches",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("batch_key", sa.String(length=80), nullable=False),
        sa.Column("nombre", sa.String(length=160), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="BORRADOR",
            nullable=False,
        ),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("source_filename", sa.String(length=255), nullable=True),
        sa.Column("source_sha256", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("published_by_user_id", sa.Integer(), nullable=True),
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
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "source_type IN ('MANUAL', 'ARCHIVO')",
            name="ck_maintenance_preventive_batches_source_type",
        ),
        sa.CheckConstraint(
            "status IN ('BORRADOR', 'PUBLICADO', 'CANCELADO')",
            name="ck_maintenance_preventive_batches_status",
        ),
        sa.CheckConstraint(
            "period_start IS NULL OR period_end IS NULL "
            "OR period_start <= period_end",
            name="ck_maintenance_preventive_batches_period",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["published_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "batch_key",
            name="uq_maintenance_preventive_batches_batch_key",
        ),
    )

    op.create_index(
        "ix_maintenance_preventive_batches_created_by_user_id",
        "maintenance_preventive_batches",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_preventive_batches_published_by_user_id",
        "maintenance_preventive_batches",
        ["published_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_preventive_batches_status",
        "maintenance_preventive_batches",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_preventive_batches_period",
        "maintenance_preventive_batches",
        ["period_start", "period_end"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_preventive_batches_source_sha256",
        "maintenance_preventive_batches",
        ["source_sha256"],
        unique=False,
    )

    op.create_table(
        "maintenance_preventive_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=True),
        sa.Column("sucursal_input", sa.String(length=160), nullable=True),
        sa.Column("codigo_equipo_input", sa.String(length=80), nullable=True),
        sa.Column("responsable_input", sa.String(length=160), nullable=True),
        sa.Column("fecha_programada_input", sa.String(length=40), nullable=True),
        sa.Column("sucursal_id", sa.Integer(), nullable=True),
        sa.Column("inventario_id", sa.Integer(), nullable=True),
        sa.Column("responsable_user_id", sa.Integer(), nullable=True),
        sa.Column("fecha_programada", sa.Date(), nullable=True),
        sa.Column("actividad", sa.Text(), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column(
            "validation_status",
            sa.String(length=20),
            server_default="PENDIENTE",
            nullable=False,
        ),
        sa.Column(
            "validation_errors",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("ticket_id", sa.Integer(), nullable=True),
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
            "validation_status IN ('PENDIENTE', 'VALIDO', 'ERROR')",
            name="ck_maintenance_preventive_items_validation_status",
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["maintenance_preventive_batches.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sucursal_id"],
            ["sucursales.sucursal_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["inventario_id"],
            ["inventario_general.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["responsable_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "batch_id",
            "source_row_number",
            name="uq_maintenance_preventive_items_batch_source_row",
        ),
        sa.UniqueConstraint(
            "ticket_id",
            name="uq_maintenance_preventive_items_ticket_id",
        ),
    )

    op.create_index(
        "ix_maintenance_preventive_items_batch_id",
        "maintenance_preventive_items",
        ["batch_id"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_preventive_items_sucursal_id",
        "maintenance_preventive_items",
        ["sucursal_id"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_preventive_items_inventario_id",
        "maintenance_preventive_items",
        ["inventario_id"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_preventive_items_responsable_user_id",
        "maintenance_preventive_items",
        ["responsable_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_preventive_items_fecha_programada",
        "maintenance_preventive_items",
        ["fecha_programada"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_preventive_items_batch_validation",
        "maintenance_preventive_items",
        ["batch_id", "validation_status"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_preventive_items_schedule",
        "maintenance_preventive_items",
        ["fecha_programada", "sucursal_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_maintenance_preventive_items_schedule",
        table_name="maintenance_preventive_items",
    )
    op.drop_index(
        "ix_maintenance_preventive_items_batch_validation",
        table_name="maintenance_preventive_items",
    )
    op.drop_index(
        "ix_maintenance_preventive_items_fecha_programada",
        table_name="maintenance_preventive_items",
    )
    op.drop_index(
        "ix_maintenance_preventive_items_responsable_user_id",
        table_name="maintenance_preventive_items",
    )
    op.drop_index(
        "ix_maintenance_preventive_items_inventario_id",
        table_name="maintenance_preventive_items",
    )
    op.drop_index(
        "ix_maintenance_preventive_items_sucursal_id",
        table_name="maintenance_preventive_items",
    )
    op.drop_index(
        "ix_maintenance_preventive_items_batch_id",
        table_name="maintenance_preventive_items",
    )
    op.drop_table("maintenance_preventive_items")

    op.drop_index(
        "ix_maintenance_preventive_batches_source_sha256",
        table_name="maintenance_preventive_batches",
    )
    op.drop_index(
        "ix_maintenance_preventive_batches_period",
        table_name="maintenance_preventive_batches",
    )
    op.drop_index(
        "ix_maintenance_preventive_batches_status",
        table_name="maintenance_preventive_batches",
    )
    op.drop_index(
        "ix_maintenance_preventive_batches_published_by_user_id",
        table_name="maintenance_preventive_batches",
    )
    op.drop_index(
        "ix_maintenance_preventive_batches_created_by_user_id",
        table_name="maintenance_preventive_batches",
    )
    op.drop_table("maintenance_preventive_batches")
