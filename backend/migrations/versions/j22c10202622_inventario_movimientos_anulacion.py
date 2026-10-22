"""Anulación auditada de movimientos sin borrar el historial.

Revision ID: j22c10202622
Revises: i22c10202622
Create Date: 2026-10-22
"""

from alembic import op
import sqlalchemy as sa

revision = "j22c10202622"
down_revision = "i22c10202622"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "movimientos_inventario",
        sa.Column("anulado", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "movimientos_inventario",
        sa.Column("anulado_por_usuario_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "movimientos_inventario",
        sa.Column("anulado_en_utc", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "movimientos_inventario",
        sa.Column("motivo_anulacion", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_mov_inv_anulado_por_usuario",
        "movimientos_inventario",
        "users",
        ["anulado_por_usuario_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_mov_inv_anulacion_auditada_completa",
        "movimientos_inventario",
        """(
            anulado = false
            AND anulado_por_usuario_id IS NULL
            AND anulado_en_utc IS NULL
            AND motivo_anulacion IS NULL
        ) OR (
            anulado = true
            AND anulado_por_usuario_id IS NOT NULL
            AND anulado_en_utc IS NOT NULL
            AND NULLIF(BTRIM(motivo_anulacion), '') IS NOT NULL
        )""",
    )


def downgrade():
    count = op.get_bind().execute(
        sa.text("SELECT COUNT(*) FROM movimientos_inventario WHERE anulado = true")
    ).scalar_one()
    if count:
        raise RuntimeError(
            "No se puede descartar la auditoría: existen movimientos anulados."
        )

    op.drop_constraint(
        "ck_mov_inv_anulacion_auditada_completa",
        "movimientos_inventario",
        type_="check",
    )
    op.drop_constraint(
        "fk_mov_inv_anulado_por_usuario",
        "movimientos_inventario",
        type_="foreignkey",
    )
    for name in (
        "motivo_anulacion",
        "anulado_en_utc",
        "anulado_por_usuario_id",
        "anulado",
    ):
        op.drop_column("movimientos_inventario", name)
