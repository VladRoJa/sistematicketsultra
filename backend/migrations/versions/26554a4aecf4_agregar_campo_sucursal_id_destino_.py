"""Agregar campo sucursal_id_destino obligatorio a tickets

Revision ID: 26554a4aecf4
Revises: 708ba4302146
Create Date: 2025-08-08 12:26:58.418020
"""
from alembic import op
import sqlalchemy as sa

# identifiers
revision = "26554a4aecf4"
down_revision = "708ba4302146"
branch_labels = None
depends_on = None


def upgrade():
    # 1) crear columna como nullable para poder rellenarla
    with op.batch_alter_table("tickets") as batch_op:
        batch_op.add_column(sa.Column("sucursal_id_destino", sa.Integer(), nullable=True))

    # 2) rellenar con un valor válido (preferir sucursal_id existente; fallback 1)
    op.execute("""
        UPDATE tickets
        SET sucursal_id_destino = COALESCE(
            sucursal_id,
            (SELECT MIN(sucursal_id) FROM sucursales)
        )
        WHERE sucursal_id_destino IS NULL
    """)


    # 3) volverla NOT NULL y crear la FK a sucursales.sucursal_id
    with op.batch_alter_table("tickets") as batch_op:
        batch_op.alter_column("sucursal_id_destino", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            "fk_tickets_sucursal_id_destino",
            "sucursales",
            ["sucursal_id_destino"],
            ["sucursal_id"],
            ondelete="CASCADE",
        )


def downgrade():
    with op.batch_alter_table("tickets") as batch_op:
        batch_op.drop_constraint("fk_tickets_sucursal_id_destino", type_="foreignkey")
        batch_op.drop_column("sucursal_id_destino")
