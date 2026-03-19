from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ddd1eae8b99d'
down_revision = '8ce7fa8b6387'
branch_labels = None
depends_on = None


warehouse_families_table = sa.table(
    'warehouse_families',
    sa.column('key', sa.String(length=80)),
    sa.column('label', sa.String(length=150)),
    sa.column('active', sa.Boolean()),
)


def upgrade():
    op.bulk_insert(
        warehouse_families_table,
        [
            {
                'key': 'kpi_snapshot',
                'label': 'KPI Snapshot',
                'active': True,
            },
            {
                'key': 'reportes_transaccionales',
                'label': 'Reportes Transaccionales',
                'active': True,
            },
            {
                'key': 'catalogos_auxiliares',
                'label': 'Catálogos Auxiliares',
                'active': True,
            },
        ]
    )


def downgrade():
    op.execute(
        """
        DELETE FROM warehouse_families
        WHERE key IN (
            'kpi_snapshot',
            'reportes_transaccionales',
            'catalogos_auxiliares'
        )
        """
    )