"""Opaque rotating refresh credentials with persistent revocation.

Every refresh is a database transaction. The row lock serializes simultaneous
requests, and reuse of a rotated credential revokes that browser session.
"""
import hashlib
import hmac
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from flask import current_app

from app.extensions import db
from app.models.auth_refresh_session import AuthRefreshSessionORM
from app.models.user_model import UserORM


class RefreshDenied(Exception):
    def __init__(self, code="SESSION_INVALID"):
        self.code = code
        super().__init__(code)


def utc_now():
    return datetime.now(timezone.utc)


def _aware_utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_cookie(value):
    if not isinstance(value, str) or len(value) != 97:
        raise RefreshDenied()
    session_id, separator, secret = value.partition(".")
    if (
        separator != "."
        or re.fullmatch(r"[0-9a-f]{32}", session_id) is None
        or re.fullmatch(r"[A-Za-z0-9_-]{64}", secret) is None
    ):
        raise RefreshDenied()
    return session_id, secret


def _digest(secret):
    return hashlib.sha256(secret.encode("ascii")).hexdigest()


def _new_secret():
    return secrets.token_urlsafe(48)  # 384 bits, 64 base64url chars


def _idle_window():
    return timedelta(minutes=int(current_app.config["AUTH_REFRESH_IDLE_MINUTES"]))


def _absolute_window():
    return timedelta(hours=int(current_app.config["AUTH_REFRESH_ABSOLUTE_HOURS"]))


def issue_refresh(user_id):
    """Issue a session after password verification; store digest only."""
    now = utc_now()
    secret = _new_secret()
    session_id = uuid.uuid4().hex
    expiry = now + _absolute_window()

    db.session.add(
        AuthRefreshSessionORM(
            id=session_id,
            user_id=int(user_id),
            refresh_hash=_digest(secret),
            created_at=now,
            last_activity_at=now,
            idle_expires_at=min(now + _idle_window(), expiry),
            absolute_expires_at=expiry,
            rotation_count=0,
        )
    )
    db.session.commit()
    return session_id + "." + secret, session_id


def rotate_refresh(raw_cookie):
    """Rotate once, under row lock, and re-read user permissions from DB."""
    session_id, secret = _parse_cookie(raw_cookie)
    row = (
        AuthRefreshSessionORM.query
        .filter_by(id=session_id)
        .with_for_update()
        .one_or_none()
    )
    if row is None or row.revoked_at is not None:
        raise RefreshDenied()

    now = utc_now()
    if not hmac.compare_digest(row.refresh_hash, _digest(secret)):
        row.revoked_at = now
        row.revoke_reason = "REPLAY"
        db.session.commit()
        raise RefreshDenied("SESSION_REPLAYED")

    if (
        now >= _aware_utc(row.idle_expires_at)
        or now >= _aware_utc(row.absolute_expires_at)
    ):
        row.revoked_at = now
        row.revoke_reason = "EXPIRED"
        db.session.commit()
        raise RefreshDenied("SESSION_EXPIRED")

    user = UserORM.get_by_id(row.user_id)
    if user is None:
        row.revoked_at = now
        row.revoke_reason = "USER_REMOVED"
        db.session.commit()
        raise RefreshDenied()

    new_secret = _new_secret()
    row.refresh_hash = _digest(new_secret)
    row.last_activity_at = now
    row.idle_expires_at = min(
        now + _idle_window(), _aware_utc(row.absolute_expires_at)
    )
    row.rotation_count += 1
    db.session.commit()
    return user, session_id + "." + new_secret, session_id


def revoke_refresh(raw_cookie):
    """Logout is idempotent; a stale secret also invalidates this session."""
    try:
        session_id, _ = _parse_cookie(raw_cookie)
    except RefreshDenied:
        return
    row = (
        AuthRefreshSessionORM.query
        .filter_by(id=session_id)
        .with_for_update()
        .one_or_none()
    )
    if row is not None and row.revoked_at is None:
        row.revoked_at = utc_now()
        row.revoke_reason = "LOGOUT"
        db.session.commit()


def is_access_revoked(_jwt_header, jwt_payload):
    """Enforce logout on new session-bound JWTs; legacy JWTs expire as before."""
    session_id = jwt_payload.get("sid")
    if not session_id:
        return False  # Existing tokens during controlled rollout.
    row = db.session.get(AuthRefreshSessionORM, session_id)
    if row is None or row.revoked_at is not None:
        return True
    now = utc_now()
    return (
        now >= _aware_utc(row.idle_expires_at)
        or now >= _aware_utc(row.absolute_expires_at)
    )
