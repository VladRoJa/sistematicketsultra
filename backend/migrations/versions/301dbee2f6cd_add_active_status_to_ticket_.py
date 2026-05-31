"""add active status to ticket classifications

Revision ID: 301dbee2f6cd
Revises: 1927b6e90cfa
Create Date: 2026-05-31 11:52:26.419994

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '301dbee2f6cd'
down_revision = '1927b6e90cfa'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'catalogo_clasificacion',
        sa.Column(
            'activo',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('true')
        )
    )
    op.add_column(
        'catalogo_clasificacion',
        sa.Column(
            'creado_en',
            sa.DateTime(),
            nullable=True,
            server_default=sa.text('now()')
        )
    )
    op.add_column(
        'catalogo_clasificacion',
        sa.Column(
            'actualizado_en',
            sa.DateTime(),
            nullable=True
        )
    )


def downgrade():
    op.drop_column('catalogo_clasificacion', 'actualizado_en')
    op.drop_column('catalogo_clasificacion', 'creado_en')
    op.drop_column('catalogo_clasificacion', 'activo')
