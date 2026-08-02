"""add routine matching v2 audit

Revision ID: e1b7c9d2a4f6
Revises: d9a3e7b5c102
Create Date: 2026-07-31 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "e1b7c9d2a4f6"
down_revision = "d9a3e7b5c102"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "routine_assignment_evidences",
        sa.Column("member_name_original", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "routine_assignment_evidences",
        sa.Column("member_name_normalized", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "routine_control_member_evidences",
        sa.Column("identity_corroborator", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "routine_control_member_evidences",
        sa.Column("temporal_delta_days", sa.Integer(), nullable=True),
    )
    op.add_column(
        "routine_control_member_evidences",
        sa.Column("matching_contract_version", sa.String(length=80), nullable=True),
    )


def downgrade():
    op.drop_column(
        "routine_control_member_evidences",
        "matching_contract_version",
    )
    op.drop_column(
        "routine_control_member_evidences",
        "temporal_delta_days",
    )
    op.drop_column(
        "routine_control_member_evidences",
        "identity_corroborator",
    )
    op.drop_column(
        "routine_assignment_evidences",
        "member_name_normalized",
    )
    op.drop_column(
        "routine_assignment_evidences",
        "member_name_original",
    )
