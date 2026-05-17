"""add core truth constraints for pm and inventory

Revision ID: 37d51eb7ff9c
Revises: 840a64d2ee63
Create Date: 2026-05-16 20:11:52.907850

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '37d51eb7ff9c'
down_revision = '840a64d2ee63'
branch_labels = None
depends_on = None


def upgrade():
    # 1. pm_bitacoras.sucursal_id debe apuntar a sucursales.sucursal_id
    op.create_foreign_key(
        "fk_pm_bitacoras_sucursal_id_sucursales",
        "pm_bitacoras",
        "sucursales",
        ["sucursal_id"],
        ["sucursal_id"],
        ondelete="CASCADE",
    )

    # 2. resultado PM limitado a catálogo válido
    op.create_check_constraint(
        "ck_pm_bitacoras_resultado",
        "pm_bitacoras",
        "resultado IN ('OK', 'FALLA', 'OBS')",
    )

    # 3. tipo_mantenimiento PM limitado a catálogo válido
    op.create_check_constraint(
        "ck_pm_bitacoras_tipo_mantenimiento",
        "pm_bitacoras",
        "tipo_mantenimiento IN ('PREVENTIVO', 'CORRECTIVO', 'ESTETICO', 'MEJORA')",
    )

    # 4. inventario_sucursal no debe duplicar el mismo activo en la misma sucursal
    op.create_unique_constraint(
        "uq_inventario_sucursal_activo",
        "inventario_sucursal",
        ["inventario_id", "sucursal_id"],
    )


def downgrade():
    # Revertir en orden inverso

    op.drop_constraint(
        "uq_inventario_sucursal_activo",
        "inventario_sucursal",
        type_="unique",
    )

    op.drop_constraint(
        "ck_pm_bitacoras_tipo_mantenimiento",
        "pm_bitacoras",
        type_="check",
    )

    op.drop_constraint(
        "ck_pm_bitacoras_resultado",
        "pm_bitacoras",
        type_="check",
    )

    op.drop_constraint(
        "fk_pm_bitacoras_sucursal_id_sucursales",
        "pm_bitacoras",
        type_="foreignkey",
    )