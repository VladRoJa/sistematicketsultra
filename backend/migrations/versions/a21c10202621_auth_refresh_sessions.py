"""Persist revocable browser sessions for rotating auth refresh.

Revision ID: a21c10202621
Revises: f22c10202601
Create Date: 2026-10-21

Only the session identifier and hash of the secret are persisted.
No existing sessions or users are altered.
"""
from alembic import op
import sqlalchemy as sa

revision = "a21c10202621"
down_revision = "f22c10202601"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "auth_refresh_sessions",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("refresh_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.String(32), nullable=True),
        sa.Column("rotation_count", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.PrimaryKeyConstraint("id", name="pk_auth_refresh_sessions"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"],
                                name="fk_auth_refresh_sessions_user",
                                ondelete="CASCADE"),
        sa.UniqueConstraint("refresh_hash", name="uq_auth_refresh_hash"),
        sa.CheckConstraint("rotation_count >= 0",
                           name="ck_auth_refresh_rotation_nonnegative"),
    )
    op.create_index("ix_auth_refresh_sessions_user_id",
                    "auth_refresh_sessions", ["user_id"])


def downgrade():
    count = op.get_bind().execute(
        sa.text("SELECT COUNT(*) FROM auth_refresh_sessions")
    ).scalar_one()
    if count:
        raise RuntimeError(
            "No se puede borrar sesiones de autenticación sin revocarlas "
            "y respaldarlas primero."
        )
    op.drop_index("ix_auth_refresh_sessions_user_id",
                  table_name="auth_refresh_sessions")
    op.drop_table("auth_refresh_sessions")
