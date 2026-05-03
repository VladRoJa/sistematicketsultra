"""add track daily version id to track daily mart

Revision ID: 359ea7512b12
Revises: 320db239c791
Create Date: 2026-05-02 16:13:21.892100

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '359ea7512b12'
down_revision = '320db239c791'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "track_daily_mart",
        sa.Column("track_daily_version_id", sa.BigInteger(), nullable=True),
    )

    op.create_foreign_key(
        "fk_track_daily_mart_track_daily_version_id",
        "track_daily_mart",
        "track_daily_versions",
        ["track_daily_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(
        "ix_track_daily_mart_track_daily_version_id",
        "track_daily_mart",
        ["track_daily_version_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_track_daily_mart_track_daily_version_id",
        table_name="track_daily_mart",
    )

    op.drop_constraint(
        "fk_track_daily_mart_track_daily_version_id",
        "track_daily_mart",
        type_="foreignkey",
    )

    op.drop_column("track_daily_mart", "track_daily_version_id")