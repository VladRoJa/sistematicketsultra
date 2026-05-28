"""create planning operators table

Revision ID: 1927b6e90cfa
Revises: 50f1c90f156e
Create Date: 2026-05-27 12:42:36.028909

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1927b6e90cfa'
down_revision = '50f1c90f156e'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "planning_operators",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("can_view", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("can_edit", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_submit", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_approve", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_publish", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_configure_model", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("added_by_user_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
            ["user_id"],
            ["users.id"],
            name="fk_planning_operators_user_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["added_by_user_id"],
            ["users.id"],
            name="fk_planning_operators_added_by_user_id",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "user_id",
            name="uq_planning_operators_user_id",
        ),
    )

    op.create_index(
        "ix_planning_operators_user_id",
        "planning_operators",
        ["user_id"],
    )
    op.create_index(
        "ix_planning_operators_added_by_user_id",
        "planning_operators",
        ["added_by_user_id"],
    )
    op.create_index(
        "ix_planning_operators_is_active",
        "planning_operators",
        ["is_active"],
    )


def downgrade():
    op.drop_index(
        "ix_planning_operators_is_active",
        table_name="planning_operators",
    )
    op.drop_index(
        "ix_planning_operators_added_by_user_id",
        table_name="planning_operators",
    )
    op.drop_index(
        "ix_planning_operators_user_id",
        table_name="planning_operators",
    )
    op.drop_table("planning_operators")