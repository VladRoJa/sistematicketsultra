"""seed warehouse operational roles

Revision ID: 43907668e3f4
Revises: ddd1eae8b99d
Create Date: 2026-03-18 22:06:47.001095

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '43907668e3f4'
down_revision = 'ddd1eae8b99d'
branch_labels = None
depends_on = None

warehouse_operational_roles_table = sa.table(
    'warehouse_operational_roles',
    sa.column('key', sa.String(length=80)),
    sa.column('label', sa.String(length=150)),
    sa.column('active', sa.Boolean()),
)


def upgrade():
    op.bulk_insert(
        warehouse_operational_roles_table,
        [
            {
                'key': 'FUENTE_PRINCIPAL',
                'label': 'Fuente Principal',
                'active': True,
            },
            {
                'key': 'FUENTE_AUXILIAR_ENRIQUECIMIENTO',
                'label': 'Fuente Auxiliar de Enriquecimiento',
                'active': True,
            },
            {
                'key': 'CATALOGO_AUXILIAR',
                'label': 'Catálogo Auxiliar',
                'active': True,
            },
        ]
    )


def downgrade():
    op.execute(
        """
        DELETE FROM warehouse_operational_roles
        WHERE key IN (
            'FUENTE_PRINCIPAL',
            'FUENTE_AUXILIAR_ENRIQUECIMIENTO',
            'CATALOGO_AUXILIAR'
        )
        """
    )