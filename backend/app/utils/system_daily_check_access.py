from __future__ import annotations


SYSTEM_DAILY_CHECK_MVP_ROLE = "SISTEMAS"
SYSTEM_DAILY_CHECK_MVP_USERNAME = "ADMICORP"


def _normalize(value: object) -> str:
    return str(value or "").strip().upper()


def has_system_daily_check_mvp_access(user) -> bool:
    """Return whether the user is explicitly enabled for the M1/MVP rollout."""
    if user is None:
        return False

    role = _normalize(getattr(user, "rol", None))
    username = _normalize(getattr(user, "username", None))

    return (
        role == SYSTEM_DAILY_CHECK_MVP_ROLE
        or username == SYSTEM_DAILY_CHECK_MVP_USERNAME
    )
