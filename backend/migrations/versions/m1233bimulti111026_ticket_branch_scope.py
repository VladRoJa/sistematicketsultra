"""Store multiple affected branches for one BI Vlad ticket.

Revision ID: m1233bimulti111026
Revises: m1232bivlad111026
"""
from alembic import op
import sqlalchemy as sa

revision = "m1233bimulti111026"
down_revision = "m1232bivlad111026"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ticket_sucursales_alcance",
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("sucursal_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["tickets.id"],
            name="fk_ticket_sucursales_alcance_ticket", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sucursal_id"], ["sucursales.sucursal_id"],
            name="fk_ticket_sucursales_alcance_sucursal", ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("ticket_id", "sucursal_id",
                                name="pk_ticket_sucursales_alcance"),
    )
    op.create_index(
        "ix_ticket_sucursales_alcance_sucursal_id",
        "ticket_sucursales_alcance", ["sucursal_id"], unique=False,
    )


def downgrade():
    bind = op.get_bind()
    count = bind.execute(sa.text(
        "SELECT count(*) FROM ticket_sucursales_alcance"
    )).scalar_one()
    if count:
        raise RuntimeError(
            "No se puede revertir alcance BI Vlad con sucursales registradas; "
            "hay tickets operativos que conservar."
        )
    op.drop_index("ix_ticket_sucursales_alcance_sucursal_id",
                  table_name="ticket_sucursales_alcance")
    op.drop_table("ticket_sucursales_alcance")
