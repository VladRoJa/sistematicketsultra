"""M4: recepción individual de aparatos asociados a tickets de tapizado.

Revision ID: m23c10202623
Revises: v2e2a7c92623
Create Date: 2026-10-23

No backfill: los vínculos existentes quedan pendientes hasta que un operador
registre su recepción. El historial de cambios vive en tickets.historial_fechas.
"""

from alembic import op
import sqlalchemy as sa

revision = "m23c10202623"
down_revision = "v2e2a7c92623"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "ticket_aparatos",
        sa.Column("recibido_en_utc", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ticket_aparatos",
        sa.Column("recibido_por", sa.String(length=100), nullable=True),
    )
    op.create_check_constraint(
        "ck_ticket_aparatos_recepcion_par",
        "ticket_aparatos",
        "(recibido_en_utc IS NULL AND recibido_por IS NULL) OR "
        "(recibido_en_utc IS NOT NULL AND recibido_por IS NOT NULL)",
    )


def downgrade():
    has_data = op.get_bind().execute(sa.text(
        "SELECT COUNT(*) FROM ticket_aparatos WHERE recibido_en_utc IS NOT NULL"
    )).scalar_one()
    if has_data:
        raise RuntimeError("No se puede perder el historial de recepción M4.")
    op.drop_constraint(
        "ck_ticket_aparatos_recepcion_par", "ticket_aparatos", type_="check"
    )
    op.drop_column("ticket_aparatos", "recibido_por")
    op.drop_column("ticket_aparatos", "recibido_en_utc")
