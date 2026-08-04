"""add phone to routine control members

Revision ID: c81b2e6a4f90
Revises: e1b7c9d2a4f6
Create Date: 2026-08-04

"""
from alembic import op
import sqlalchemy as sa


revision = "c81b2e6a4f90"
down_revision = "e1b7c9d2a4f6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "routine_control_members",
        sa.Column(
            "phone_original",
            sa.String(length=32),
            nullable=True,
        ),
    )
    op.add_column(
        "routine_control_members",
        sa.Column(
            "phone_normalized",
            sa.String(length=32),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_routine_control_members_phone_normalized",
        "routine_control_members",
        ["phone_normalized"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_routine_control_members_phone_normalized",
        table_name="routine_control_members",
    )
    op.drop_column(
        "routine_control_members",
        "phone_normalized",
    )
    op.drop_column(
        "routine_control_members",
        "phone_original",
    )
