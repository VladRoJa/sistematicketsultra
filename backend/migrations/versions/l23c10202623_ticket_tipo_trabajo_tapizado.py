"""M2: tipo de trabajo de tapizado para tickets multiaparato.

Revision ID: l23c10202623
Revises: k23c10202623
Create Date: 2026-10-23
"""

from alembic import op
import sqlalchemy as sa


revision = "l23c10202623"
down_revision = "k23c10202623"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tickets",
        sa.Column("tipo_trabajo", sa.String(length=24), nullable=True),
    )
    op.create_check_constraint(
        "ck_tickets_tipo_trabajo_tapizado",
        "tickets",
        "tipo_trabajo IS NULL OR tipo_trabajo = 'TAPIZADO'",
    )


def downgrade():
    # Nunca perder la identidad histórica de trabajos multiaparato.
    count = op.get_bind().execute(
        sa.text("SELECT COUNT(*) FROM tickets WHERE tipo_trabajo IS NOT NULL")
    ).scalar_one()
    if count:
        raise RuntimeError(
            "No se puede descartar tipo_trabajo: existen tickets tipificados."
        )

    op.drop_constraint(
        "ck_tickets_tipo_trabajo_tapizado", "tickets", type_="check"
    )
    op.drop_column("tickets", "tipo_trabajo")
