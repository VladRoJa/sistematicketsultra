"""Join M6 correction versions and Campaign V2 USD approvals.

Revision ID: a9c6b2e4f150
Revises: c5e7a2d93f10, a856usd1015

Merge-only migration. No DDL, DML, backfill or historical data changes.
"""
revision = "a9c6b2e4f150"
down_revision = ("c5e7a2d93f10", "a856usd1015")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
