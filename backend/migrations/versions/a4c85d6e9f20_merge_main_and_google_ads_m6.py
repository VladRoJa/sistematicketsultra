"""Merge current Suite Ultra main and Google Ads M6 migration histories.

Revision ID: a4c85d6e9f20
Revises: c856map1014, d7f2a09c8b61

This is a graph-only merge. Both parent chains keep their original upgrade
operations and historic revisions. No automatic M6 approval, backfill, data
rewrite, publication or Warehouse modification happens here.
"""
from alembic import op

revision = "a4c85d6e9f20"
down_revision = ("c856map1014", "d7f2a09c8b61")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
