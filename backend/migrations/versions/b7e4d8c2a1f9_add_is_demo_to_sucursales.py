"""Add is_demo flag to sucursales.

Revision ID: b7e4d8c2a1f9
Revises: a9c4e2f1b7d3
Create Date: 2026-09-12
"""

from alembic import op
import sqlalchemy as sa


revision = "b7e4d8c2a1f9"
down_revision = "a9c4e2f1b7d3"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("sucursales", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_demo",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )
        batch_op.create_index(
            batch_op.f("ix_sucursales_is_demo"),
            ["is_demo"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("sucursales", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_sucursales_is_demo"))
        batch_op.drop_column("is_demo")
