"""Merge M6 with the subsequent Track roster migration, preserving both histories.

Revision ID: c9e1a4d6b720
Revises: a4c85d6e9f20, f6roster1014

Graph-only merge, no DDL, DML, seeds or production writes.
"""

revision = "c9e1a4d6b720"
down_revision = ("a4c85d6e9f20", "f6roster1014")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
