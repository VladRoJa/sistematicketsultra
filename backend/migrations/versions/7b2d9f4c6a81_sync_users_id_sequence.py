"""sync users id sequence

Revision ID: 7b2d9f4c6a81
Revises: 4e8c1a7d9b20
"""

from alembic import op


revision = "7b2d9f4c6a81"
down_revision = "4e8c1a7d9b20"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        SELECT setval(
            pg_get_serial_sequence('users', 'id')::regclass,
            COALESCE((SELECT MAX(id) FROM users), 1),
            EXISTS (SELECT 1 FROM users)
        );
    """)


def downgrade():
    pass
