from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8ce7fa8b6387'   
down_revision = '05c40fcc57f4'
branch_labels = None
depends_on = None


warehouse_sources_table = sa.table(
    'warehouse_sources',
    sa.column('key', sa.String(length=50)),
    sa.column('label', sa.String(length=100)),
    sa.column('active', sa.Boolean()),
)


def upgrade():
    op.bulk_insert(
        warehouse_sources_table,
        [
            {
                'key': 'gasca',
                'label': 'Gasca',
                'active': True,
            },
            {
                'key': 'manual',
                'label': 'Manual',
                'active': True,
            },
        ]
    )


def downgrade():
    op.execute(
        "DELETE FROM warehouse_sources WHERE key IN ('gasca', 'manual')"
    )