"""Tercer modo de atención de Mantenimiento: AUTOGESTION de Yuliana.

Revision ID: c21c10202601
Revises: b20c10202601
Create Date: 2026-10-20

Únicamente amplía la restricción. No modifica ni reclasifica tickets previos.
"""
from alembic import op
import sqlalchemy as sa

revision = "c21c10202601"
down_revision = "b20c10202601"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_tickets_tipo_atencion", "tickets", type_="check")
    op.create_check_constraint(
        "ck_tickets_tipo_atencion",
        "tickets",
        "tipo_atencion IS NULL OR tipo_atencion IN ('INTERNA', 'EXTERNA', 'AUTOGESTION')",
    )


def downgrade():
    connection = op.get_bind()
    count = connection.execute(sa.text(
        "SELECT COUNT(*) FROM tickets WHERE tipo_atencion = 'AUTOGESTION'"
    )).scalar_one()
    if count:
        raise RuntimeError(
            "No es seguro revertir el modo AUTOGESTION con tickets que ya lo usan."
        )
    op.drop_constraint("ck_tickets_tipo_atencion", "tickets", type_="check")
    op.create_check_constraint(
        "ck_tickets_tipo_atencion",
        "tickets",
        "tipo_atencion IS NULL OR tipo_atencion IN ('INTERNA', 'EXTERNA')",
    )
