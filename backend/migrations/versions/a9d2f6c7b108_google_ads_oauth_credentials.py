"""Create encrypted OAuth refresh-token storage for Google Ads.

Revision ID: a9d2f6c7b108
Revises: c1d5e9a7b204
Create Date: 2026-10-09
"""

from alembic import op
import sqlalchemy as sa


revision = "a9d2f6c7b108"
down_revision = "c1d5e9a7b204"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "google_ads_oauth_credentials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.String(16), nullable=False),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=False),
        sa.Column("authorized_by_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "id = 1",
            name="ck_google_ads_oauth_single_grant",
        ),
        sa.ForeignKeyConstraint(
            ["authorized_by_user_id"], ["users.id"],
            name="fk_google_ads_oauth_authorized_user", ondelete="RESTRICT",
        ),
    )


def downgrade():
    bind = op.get_bind()
    grant_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM google_ads_oauth_credentials")
    ).scalar_one()
    if grant_count:
        raise RuntimeError(
            "Google Ads OAuth grant exists. Revoke/disconnect it before downgrade."
        )
    op.drop_table("google_ads_oauth_credentials")
