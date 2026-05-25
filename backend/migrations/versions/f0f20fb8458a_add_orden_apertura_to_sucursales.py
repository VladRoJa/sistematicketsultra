"""add orden apertura to sucursales

Revision ID: f0f20fb8458a
Revises: e78e042207aa
Create Date: 2026-05-25 07:55:30.010569

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f0f20fb8458a'
down_revision = 'e78e042207aa'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "sucursales",
        sa.Column(
            "orden_apertura",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.create_index(
        "uq_sucursales_orden_apertura_not_null",
        "sucursales",
        ["orden_apertura"],
        unique=True,
        postgresql_where=sa.text("orden_apertura IS NOT NULL"),
    )


def downgrade():
    op.drop_index(
        "uq_sucursales_orden_apertura_not_null",
        table_name="sucursales",
    )

    op.drop_column(
        "sucursales",
        "orden_apertura",
    )