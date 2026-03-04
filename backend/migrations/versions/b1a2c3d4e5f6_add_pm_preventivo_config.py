"""add pm_preventivo_config

Revision ID: b1a2c3d4e5f6
Revises: 73b9fbe9ae06
Create Date: 2026-03-04 07:17:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b1a2c3d4e5f6'
down_revision = '73b9fbe9ae06'
branch_labels = None
depends_on = None


def upgrade():
    # ── 1) Crear tabla pm_preventivo_config ──
    op.create_table(
        'pm_preventivo_config',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('inventario_id', sa.Integer(), nullable=False),
        sa.Column('sucursal_id', sa.Integer(), nullable=False),
        sa.Column('frecuencia_dias', sa.Integer(), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),

        sa.ForeignKeyConstraint(['inventario_id'], ['inventario_general.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sucursal_id'], ['sucursales.sucursal_id'], ondelete='CASCADE'),
        sa.UniqueConstraint('inventario_id', 'sucursal_id', name='uq_pm_config_equipo'),
        sa.CheckConstraint('frecuencia_dias > 0', name='ck_pm_config_frecuencia_positiva'),
    )

    # ── 2) Índice compuesto en pm_preventivo_config ──
    op.create_index(
        'idx_pm_config_equipo',
        'pm_preventivo_config',
        ['inventario_id', 'sucursal_id'],
    )

    # ── 3) Índice compuesto en tabla EXISTENTE pm_bitacoras ──
    op.execute("""
    CREATE INDEX idx_pm_bitacoras_equipo
    ON pm_bitacoras (inventario_id, sucursal_id, fecha DESC);
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_pm_bitacoras_equipo;")
    op.drop_index('idx_pm_config_equipo', table_name='pm_preventivo_config')
    op.drop_table('pm_preventivo_config')
