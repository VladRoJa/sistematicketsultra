"""Add relation table for maintenance tickets with multiple apparatus.

Revision ID: k23c10202623
Revises: j22c10202622
Create Date: 2026-10-23

M1: schema only. No backfill and no V1 workflow changes.
"""

from alembic import op
import sqlalchemy as sa


revision = "k23c10202623"
down_revision = "j22c10202622"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ticket_aparatos",
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("inventario_id", sa.Integer(), nullable=False),
        sa.Column(
            "vinculado_en_utc",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            name="fk_ticket_aparatos_ticket",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["inventario_id"],
            ["inventario_general.id"],
            name="fk_ticket_aparatos_inventario",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "ticket_id",
            "inventario_id",
            name="pk_ticket_aparatos",
        ),
    )
    op.create_index(
        "ix_ticket_aparatos_inventario_ticket",
        "ticket_aparatos",
        ["inventario_id", "ticket_id"],
        unique=False,
    )


def downgrade():
    existing = op.get_bind().execute(
        sa.text("SELECT COUNT(*) FROM ticket_aparatos")
    ).scalar_one()
    if existing:
        raise RuntimeError(
            "No se puede eliminar ticket_aparatos: hay vínculos históricos. "
            "Resguardar datos y aprobar una migración de retiro primero."
        )

    op.drop_index(
        "ix_ticket_aparatos_inventario_ticket",
        table_name="ticket_aparatos",
    )
    op.drop_table("ticket_aparatos")
