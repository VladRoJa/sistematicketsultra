"""add permission grants readonly tables

Revision ID: 6a4d2c9e8f10
Revises: e542ba5dfea9
Create Date: 2026-06-28

"""

from alembic import op
import sqlalchemy as sa


revision = '6a4d2c9e8f10'
down_revision = 'e542ba5dfea9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "permission_grants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("principal_type", sa.String(length=40), nullable=False),
        sa.Column("principal_user_id", sa.Integer(), nullable=True),
        sa.Column("principal_role_key", sa.String(length=80), nullable=True),
        sa.Column("module_id", sa.Integer(), nullable=True),
        sa.Column("action_id", sa.Integer(), nullable=True),
        sa.Column("effect", sa.String(length=20), nullable=False),
        sa.Column("scope_type", sa.String(length=40), server_default="global", nullable=False),
        sa.Column("scope_branch_id", sa.Integer(), nullable=True),
        sa.Column("scope_branch_ids", sa.JSON(), nullable=True),
        sa.Column("scope_department_id", sa.Integer(), nullable=True),
        sa.Column("scope_payload", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "principal_type IN ('user', 'role')",
            name="ck_permission_grants_principal_type",
        ),
        sa.CheckConstraint(
            "effect IN ('allow', 'deny')",
            name="ck_permission_grants_effect",
        ),
        sa.CheckConstraint(
            "scope_type IN ('global', 'branch', 'branch_list', 'department', 'module', 'custom')",
            name="ck_permission_grants_scope_type",
        ),
        sa.CheckConstraint(
            "action_id IS NOT NULL OR module_id IS NOT NULL",
            name="ck_permission_grants_target_required",
        ),
        sa.ForeignKeyConstraint(["action_id"], ["permission_actions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["module_id"], ["permission_modules.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["principal_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["scope_branch_id"], ["sucursales.sucursal_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["scope_department_id"], ["departamentos.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_permission_grants_action_id", "permission_grants", ["action_id"], unique=False)
    op.create_index("ix_permission_grants_created_by_user_id", "permission_grants", ["created_by_user_id"], unique=False)
    op.create_index("ix_permission_grants_effect", "permission_grants", ["effect"], unique=False)
    op.create_index("ix_permission_grants_is_active", "permission_grants", ["is_active"], unique=False)
    op.create_index("ix_permission_grants_module_id", "permission_grants", ["module_id"], unique=False)
    op.create_index("ix_permission_grants_principal_role_key", "permission_grants", ["principal_role_key"], unique=False)
    op.create_index("ix_permission_grants_principal_type", "permission_grants", ["principal_type"], unique=False)
    op.create_index("ix_permission_grants_principal_user_id", "permission_grants", ["principal_user_id"], unique=False)
    op.create_index("ix_permission_grants_scope_branch_id", "permission_grants", ["scope_branch_id"], unique=False)
    op.create_index("ix_permission_grants_scope_department_id", "permission_grants", ["scope_department_id"], unique=False)
    op.create_index("ix_permission_grants_scope_type", "permission_grants", ["scope_type"], unique=False)
    op.create_index("ix_permission_grants_updated_by_user_id", "permission_grants", ["updated_by_user_id"], unique=False)

    op.create_table(
        "permission_grant_audit_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("grant_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("before_payload", sa.JSON(), nullable=True),
        sa.Column("after_payload", sa.JSON(), nullable=True),
        sa.Column("changed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("request_ip", sa.String(length=80), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('created', 'updated', 'disabled', 'enabled', 'deleted_soft', 'expired')",
            name="ck_permission_grant_audit_log_event_type",
        ),
        sa.ForeignKeyConstraint(["changed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["grant_id"], ["permission_grants.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_permission_grant_audit_log_changed_by_user_id", "permission_grant_audit_log", ["changed_by_user_id"], unique=False)
    op.create_index("ix_permission_grant_audit_log_created_at", "permission_grant_audit_log", ["created_at"], unique=False)
    op.create_index("ix_permission_grant_audit_log_event_type", "permission_grant_audit_log", ["event_type"], unique=False)
    op.create_index("ix_permission_grant_audit_log_grant_id", "permission_grant_audit_log", ["grant_id"], unique=False)


def downgrade():
    op.drop_index("ix_permission_grant_audit_log_grant_id", table_name="permission_grant_audit_log")
    op.drop_index("ix_permission_grant_audit_log_event_type", table_name="permission_grant_audit_log")
    op.drop_index("ix_permission_grant_audit_log_created_at", table_name="permission_grant_audit_log")
    op.drop_index("ix_permission_grant_audit_log_changed_by_user_id", table_name="permission_grant_audit_log")
    op.drop_table("permission_grant_audit_log")

    op.drop_index("ix_permission_grants_updated_by_user_id", table_name="permission_grants")
    op.drop_index("ix_permission_grants_scope_type", table_name="permission_grants")
    op.drop_index("ix_permission_grants_scope_department_id", table_name="permission_grants")
    op.drop_index("ix_permission_grants_scope_branch_id", table_name="permission_grants")
    op.drop_index("ix_permission_grants_principal_user_id", table_name="permission_grants")
    op.drop_index("ix_permission_grants_principal_type", table_name="permission_grants")
    op.drop_index("ix_permission_grants_principal_role_key", table_name="permission_grants")
    op.drop_index("ix_permission_grants_module_id", table_name="permission_grants")
    op.drop_index("ix_permission_grants_is_active", table_name="permission_grants")
    op.drop_index("ix_permission_grants_effect", table_name="permission_grants")
    op.drop_index("ix_permission_grants_created_by_user_id", table_name="permission_grants")
    op.drop_index("ix_permission_grants_action_id", table_name="permission_grants")
    op.drop_table("permission_grants")

