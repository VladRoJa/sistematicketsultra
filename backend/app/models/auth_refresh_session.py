"""Persisted rotating browser refresh sessions.

Only a SHA-256 digest of the high-entropy refresh secret is stored. All
timestamps use timezone-aware UTC values, including in PostgreSQL.
"""
from app.extensions import db


class AuthRefreshSessionORM(db.Model):
    __tablename__ = "auth_refresh_sessions"

    id = db.Column(db.String(32), primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    refresh_hash = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False)
    last_activity_at = db.Column(db.DateTime(timezone=True), nullable=False)
    idle_expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    absolute_expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    revoked_at = db.Column(db.DateTime(timezone=True), nullable=True)
    revoke_reason = db.Column(db.String(32), nullable=True)
    rotation_count = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        db.UniqueConstraint("refresh_hash", name="uq_auth_refresh_hash"),
        db.CheckConstraint("rotation_count >= 0",
                           name="ck_auth_refresh_rotation_nonnegative"),
    )
