"""create track daily versions

Revision ID: 320db239c791
Revises: 25dc171314da
Create Date: 2026-05-01 17:41:53.240420

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '320db239c791'
down_revision = '25dc171314da'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "track_daily_versions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("track_date", sa.Date(), nullable=False),

        sa.Column("version_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),

        sa.Column("generated_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at_utc", sa.DateTime(timezone=True), nullable=True),

        sa.Column(
            "is_current",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),

        sa.Column("replaces_version_id", sa.BigInteger(), nullable=True),
        sa.Column("base_version_id", sa.BigInteger(), nullable=True),

        sa.Column("requested_by", sa.Text(), nullable=True),
        sa.Column("trigger_source", sa.Text(), nullable=False),
        sa.Column(
            "retry_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),

        sa.ForeignKeyConstraint(
            ["replaces_version_id"],
            ["track_daily_versions.id"],
            name="fk_track_daily_versions_replaces_version_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["base_version_id"],
            ["track_daily_versions.id"],
            name="fk_track_daily_versions_base_version_id",
            ondelete="SET NULL",
        ),
    )

    op.create_index(
        "ix_track_daily_versions_track_date_version_type_status",
        "track_daily_versions",
        ["track_date", "version_type", "status"],
        unique=False,
    )

    op.create_index(
        "uq_track_daily_versions_current_per_day_type",
        "track_daily_versions",
        ["track_date", "version_type"],
        unique=True,
        postgresql_where=sa.text("is_current = true"),
    )


def downgrade():
    op.drop_index(
        "uq_track_daily_versions_current_per_day_type",
        table_name="track_daily_versions",
    )
    op.drop_index(
        "ix_track_daily_versions_track_date_version_type_status",
        table_name="track_daily_versions",
    )
    op.drop_table("track_daily_versions")