"""add track alert events

Revision ID: 99969d5f6a41
Revises: ada9909ac897
Create Date: 2026-05-23 19:28:24.314240

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '99969d5f6a41'
down_revision = 'ada9909ac897'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "track_alert_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("track_date", sa.Date(), nullable=False),
        sa.Column("sucursal_canon", sa.String(length=120), nullable=True),
        sa.Column("alert_code", sa.String(length=100), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("metric_value", sa.Numeric(18, 2), nullable=True),
        sa.Column("threshold_value", sa.Numeric(18, 2), nullable=True),
        sa.Column("ranking_position", sa.Integer(), nullable=True),
        sa.Column("was_sent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["sucursal_canon"],
            ["track_branch_catalog.sucursal_canon"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_track_alert_events_track_date",
        "track_alert_events",
        ["track_date"],
        unique=False,
    )
    op.create_index(
        "ix_track_alert_events_alert_code",
        "track_alert_events",
        ["alert_code"],
        unique=False,
    )
    op.create_index(
        "ix_track_alert_events_sucursal_canon",
        "track_alert_events",
        ["sucursal_canon"],
        unique=False,
    )
    op.create_index(
        "ix_track_alert_events_was_sent",
        "track_alert_events",
        ["was_sent"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_track_alert_events_was_sent",
        table_name="track_alert_events",
    )
    op.drop_index(
        "ix_track_alert_events_sucursal_canon",
        table_name="track_alert_events",
    )
    op.drop_index(
        "ix_track_alert_events_alert_code",
        table_name="track_alert_events",
    )
    op.drop_index(
        "ix_track_alert_events_track_date",
        table_name="track_alert_events",
    )

    op.drop_table("track_alert_events")