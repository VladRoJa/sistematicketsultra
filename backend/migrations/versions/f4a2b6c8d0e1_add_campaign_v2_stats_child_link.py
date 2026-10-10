"""Link Campaign V2 stats snapshots to provider children.

Revision ID: f4a2b6c8d0e1
Revises: f3f1d4e6a7c9
"""

from alembic import op
import sqlalchemy as sa

revision = "f4a2b6c8d0e1"
down_revision = "f3f1d4e6a7c9"
branch_labels = None
depends_on = None

TABLE = "marketing_campaign_v2_provider_stats_snapshots"
COLUMN = "provider_campaign_child_id"
FK = "fk_mkt_v2_stats_provider_campaign_child"
INDEX = "ix_mkt_v2_stats_provider_campaign_child"


def upgrade():
    op.add_column(TABLE, sa.Column(COLUMN, sa.BigInteger(), nullable=True))
    op.create_foreign_key(FK, TABLE, "marketing_campaign_v2_provider_campaigns", [COLUMN], ["id"], ondelete="SET NULL")
    op.create_index(INDEX, TABLE, [COLUMN])


def downgrade():
    op.drop_index(INDEX, table_name=TABLE)
    op.drop_constraint(FK, TABLE, type_="foreignkey")
    op.drop_column(TABLE, COLUMN)
