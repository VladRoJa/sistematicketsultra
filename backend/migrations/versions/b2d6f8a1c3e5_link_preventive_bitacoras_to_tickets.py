"""link preventive bitacoras to tickets

Revision ID: b2d6f8a1c3e5
Revises: a1c5e7f9b2d4
Create Date: 2026-09-18
"""

from alembic import op
import sqlalchemy as sa


revision = "b2d6f8a1c3e5"
down_revision = "a1c5e7f9b2d4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "pm_bitacoras",
        sa.Column("ticket_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "pm_bitacoras",
        sa.Column("estado_encontrado", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "pm_bitacoras",
        sa.Column(
            "hallazgo_detectado",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "pm_bitacoras",
        sa.Column("hallazgo_descripcion", sa.Text(), nullable=True),
    )

    op.create_foreign_key(
        "fk_pm_bitacoras_ticket_id",
        "pm_bitacoras",
        "tickets",
        ["ticket_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_pm_bitacoras_estado_encontrado",
        "pm_bitacoras",
        "estado_encontrado IS NULL OR estado_encontrado IN "
        "('BUENO', 'REQUIERE_ATENCION', 'FUERA_SERVICIO')",
    )
    op.create_index(
        "ix_pm_bitacoras_ticket_id",
        "pm_bitacoras",
        ["ticket_id"],
        unique=False,
    )
    op.create_index(
        "ix_pm_bitacoras_ticket_created",
        "pm_bitacoras",
        ["ticket_id", "created_at"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_pm_bitacoras_ticket_created",
        table_name="pm_bitacoras",
    )
    op.drop_index(
        "ix_pm_bitacoras_ticket_id",
        table_name="pm_bitacoras",
    )
    op.drop_constraint(
        "ck_pm_bitacoras_estado_encontrado",
        "pm_bitacoras",
        type_="check",
    )
    op.drop_constraint(
        "fk_pm_bitacoras_ticket_id",
        "pm_bitacoras",
        type_="foreignkey",
    )
    op.drop_column("pm_bitacoras", "hallazgo_descripcion")
    op.drop_column("pm_bitacoras", "hallazgo_detectado")
    op.drop_column("pm_bitacoras", "estado_encontrado")
    op.drop_column("pm_bitacoras", "ticket_id")
