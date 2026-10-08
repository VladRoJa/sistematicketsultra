"""Pure retry policy for Campaign V2 provider children."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


MAX_SAFE_RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = {
    0: 0,
    1: 60,
    2: 300,
}


def retry_is_exhausted(completed_attempts: int) -> bool:
    return int(completed_attempts or 0) >= MAX_SAFE_RETRY_ATTEMPTS


def next_retry_allowed_at(
    *,
    completed_attempts: int,
    resolved_at: datetime,
) -> datetime | None:
    attempts = max(0, int(completed_attempts or 0))
    if retry_is_exhausted(attempts):
        return None

    delay = RETRY_BACKOFF_SECONDS.get(attempts)
    if delay is None:
        delay = RETRY_BACKOFF_SECONDS[max(RETRY_BACKOFF_SECONDS)]

    current = resolved_at
    if current.tzinfo is None or current.utcoffset() is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)

    return current + timedelta(seconds=int(delay))
