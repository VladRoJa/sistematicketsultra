"""add global permissions readonly catalog

Revision ID: 9a7c3d5e1b2f
Revises: ca315822669e
Create Date: 2026-06-25

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9a7c3d5e1b2f"
down_revision = "ca315822669e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "permission_modules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_permission_modules_key"),
    )
    op.create_table(
        "permission_actions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("module_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("full_key", sa.String(length=240), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("risk_level", sa.String(length=40), nullable=False, server_default=sa.text("'medium'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["module_id"],
            ["permission_modules.id"],
            name="fk_permission_actions_module_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("full_key", name="uq_permission_actions_full_key"),
        sa.UniqueConstraint("module_id", "key", name="uq_permission_actions_module_key"),
    )
    op.create_index(
        "ix_permission_actions_module_id",
        "permission_actions",
        ["module_id"],
        unique=False,
    )

    op.create_table(
        "permission_route_map",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("route", sa.Text(), nullable=False),
        sa.Column("endpoint_function", sa.String(length=180), nullable=False),
        sa.Column("source_file", sa.Text(), nullable=False),
        sa.Column("module_id", sa.Integer(), nullable=True),
        sa.Column("action_id", sa.Integer(), nullable=True),
        sa.Column("current_guard", sa.Text(), nullable=True),
        sa.Column("current_scope", sa.Text(), nullable=True),
        sa.Column("review_status", sa.String(length=80), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["module_id"],
            ["permission_modules.id"],
            name="fk_permission_route_map_module_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["action_id"],
            ["permission_actions.id"],
            name="fk_permission_route_map_action_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "method",
            "route",
            "endpoint_function",
            name="uq_permission_route_map_method_route_endpoint",
        ),
    )
    op.create_index(
        "ix_permission_route_map_module_id",
        "permission_route_map",
        ["module_id"],
        unique=False,
    )
    op.create_index(
        "ix_permission_route_map_action_id",
        "permission_route_map",
        ["action_id"],
        unique=False,
    )
    op.create_index(
        "ix_permission_route_map_endpoint_function",
        "permission_route_map",
        ["endpoint_function"],
        unique=False,
    )
    op.create_index(
        "ix_permission_route_map_review_status",
        "permission_route_map",
        ["review_status"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_permission_route_map_review_status",
        table_name="permission_route_map",
    )
    op.drop_index(
        "ix_permission_route_map_endpoint_function",
        table_name="permission_route_map",
    )
    op.drop_index(
        "ix_permission_route_map_action_id",
        table_name="permission_route_map",
    )
    op.drop_index(
        "ix_permission_route_map_module_id",
        table_name="permission_route_map",
    )
    op.drop_table("permission_route_map")

    op.drop_index(
        "ix_permission_actions_module_id",
        table_name="permission_actions",
    )
    op.drop_table("permission_actions")

    op.drop_table("permission_modules")
