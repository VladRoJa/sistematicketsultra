"""Preserve immutable history of inventory internal-code corrections.

Revision ID: i22c10202622
Revises: g21c10202601
Create Date: 2026-10-22
"""
from alembic import op
import sqlalchemy as sa

revision = "i22c10202622"
down_revision = "g21c10202601"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "inventario_codigo_correcciones",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("inventario_id", sa.Integer(), nullable=False),
        sa.Column("actor_usuario_id", sa.Integer(), nullable=False),
        sa.Column("codigo_anterior", sa.String(length=50), nullable=False),
        sa.Column("codigo_nuevo", sa.String(length=50), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=False),
        sa.Column(
            "ocurrido_en_utc",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["inventario_id"], ["inventario_general.id"],
            name="fk_inv_codigo_correcciones_inventario",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_inv_codigo_correcciones_inventario",
        "inventario_codigo_correcciones",
        ["inventario_id", "ocurrido_en_utc"],
    )


def downgrade():
    count = op.get_bind().execute(
        sa.text("SELECT COUNT(*) FROM inventario_codigo_correcciones")
    ).scalar_one()
    if count:
        raise RuntimeError(
            "No se puede descartar el historial de correcciones sin respaldo."
        )
    op.drop_index(
        "ix_inv_codigo_correcciones_inventario",
        table_name="inventario_codigo_correcciones",
    )
    op.drop_table("inventario_codigo_correcciones")
