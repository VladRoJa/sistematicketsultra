"""Add contacts_count to iVentas raw pages.

Revision ID: a41c9e7b62d0
Revises: e91d7b2c4a10
Create Date: 2026-08-10

contacts_count conserva la cantidad de objetos contacto
obtenidos después de parsear correctamente una raw page.

NULL significa raw capturado todavía no parseado.
0 significa parse correcto sin contactos.
N > 0 significa parse correcto con N contactos.
"""

from alembic import op
import sqlalchemy as sa


revision = "a41c9e7b62d0"
down_revision = "e91d7b2c4a10"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "marketing_iventas_raw_pages",
        sa.Column(
            "contacts_count",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.create_check_constraint(
        "ck_marketing_iventas_raw_pages_contacts_count_nonnegative",
        "marketing_iventas_raw_pages",
        (
            "contacts_count IS NULL "
            "OR contacts_count >= 0"
        ),
    )


def downgrade():
    op.drop_constraint(
        "ck_marketing_iventas_raw_pages_contacts_count_nonnegative",
        "marketing_iventas_raw_pages",
        type_="check",
    )

    op.drop_column(
        "marketing_iventas_raw_pages",
        "contacts_count",
    )
