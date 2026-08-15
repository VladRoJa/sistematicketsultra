"""add routine control sale at utc

Revision ID: 079b090bd487
Revises: a41c9e7b62d0
Create Date: 2026-08-15 13:04:17.320315

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "079b090bd487"
down_revision = "a41c9e7b62d0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "routine_control_members",
        sa.Column(
            "sale_at_utc",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade():
    op.drop_column(
        "routine_control_members",
        "sale_at_utc",
    )
