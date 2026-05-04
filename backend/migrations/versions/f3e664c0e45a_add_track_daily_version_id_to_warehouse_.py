"""add track daily version id to warehouse uploads

Revision ID: f3e664c0e45a
Revises: 37ef17686d18
Create Date: 2026-05-03 18:44:59.824101

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f3e664c0e45a'
down_revision = '37ef17686d18'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "warehouse_uploads",
        sa.Column(
            "track_daily_version_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.create_foreign_key(
        "fk_warehouse_uploads_track_daily_version_id",
        "warehouse_uploads",
        "track_daily_versions",
        ["track_daily_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(
        "idx_warehouse_uploads_track_daily_version_id",
        "warehouse_uploads",
        ["track_daily_version_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "idx_warehouse_uploads_track_daily_version_id",
        table_name="warehouse_uploads",
    )

    op.drop_constraint(
        "fk_warehouse_uploads_track_daily_version_id",
        "warehouse_uploads",
        type_="foreignkey",
    )

    op.drop_column(
        "warehouse_uploads",
        "track_daily_version_id",
    )