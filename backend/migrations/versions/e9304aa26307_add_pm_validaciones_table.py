"""add pm_validaciones table

Revision ID: e9304aa26307
Revises: b1a2c3d4e5f6
Create Date: 2026-03-08 00:57:27.943155

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e9304aa26307"
down_revision = "b1a2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pm_validaciones",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bitacora_pm_id", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("validado_por_user_id", sa.Integer(), nullable=False),
        sa.Column("validado_en", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision IN ('VALIDADO', 'RECHAZADO')",
            name="ck_pm_validaciones_decision",
        ),
        sa.ForeignKeyConstraint(
            ["bitacora_pm_id"],
            ["pm_bitacoras.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["validado_por_user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bitacora_pm_id"),
    )
    op.create_index(
        op.f("ix_pm_validaciones_validado_por_user_id"),
        "pm_validaciones",
        ["validado_por_user_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_pm_validaciones_validado_por_user_id"), table_name="pm_validaciones")
    op.drop_table("pm_validaciones")