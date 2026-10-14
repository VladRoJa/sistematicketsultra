"""Scheduler health is based only on persisted instance heartbeats.

Never confuses worker liveness, individual job result, or data freshness.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.extensions import db
from app.models.automation_control import SystemWorkerHeartbeatORM
from app.services.automation_control.job_catalog import get_job_catalog
from app.services.automation_control.effective_schedule_service import validate_schedule_snapshot

LOGGER = logging.getLogger(__name__)
_INSTANCE_ID = uuid4().hex
_STARTED_AT = datetime.now(timezone.utc)
_REPORTED_FAILURES: set[str] = set()


def emit_worker_heartbeat(
    worker_key: str, *, poll_interval_seconds: int, enabled: bool = True,
    schedules_provider: Callable[[], dict] | None = None,
) -> None:
    """Best effort independent write; database/monitoring failures never stop jobs."""
    if worker_key not in {job.worker_key for job in get_job_catalog()}:
        raise ValueError("Unknown worker_key")
    if not isinstance(poll_interval_seconds, int) or isinstance(poll_interval_seconds, bool):
        raise ValueError("poll_interval_seconds must be an integer")
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be a boolean")
    interval = max(10, min(poll_interval_seconds, 3600))
    schedule_data = None
    if schedules_provider is not None:
        try:
            schedule_data = validate_schedule_snapshot(worker_key, schedules_provider())
        except Exception as exc:
            # Keep heartbeat alive even when optional schedule resolution fails.
            LOGGER.warning("Effective schedule unavailable worker=%s error_type=%s",
                           worker_key, type(exc).__name__)
    payload = {
        "job_schedules": schedule_data,
        "worker_key": worker_key, "instance_id": _INSTANCE_ID,
        "started_at": _STARTED_AT, "last_seen_at": datetime.now(timezone.utc),
        "poll_interval_seconds": interval, "enabled": enabled,
    }
    try:
        stmt = pg_insert(SystemWorkerHeartbeatORM).values(**payload)
        stmt = stmt.on_conflict_do_update(
            index_elements=["worker_key", "instance_id"],
            set_={
                "last_seen_at": stmt.excluded.last_seen_at,
                "poll_interval_seconds": stmt.excluded.poll_interval_seconds,
                "enabled": stmt.excluded.enabled,
                "job_schedules": stmt.excluded.job_schedules,
            },
        )
        # Important: NEVER db.session.commit() (would commit a live job).
        with db.engine.begin() as connection:
            connection.execute(stmt)
        _REPORTED_FAILURES.discard(worker_key)
    except Exception as exc:
        # Do not print connection URLs or credentials from SQLAlchemy exceptions.
        if worker_key not in _REPORTED_FAILURES:
            LOGGER.warning("Heartbeat unavailable worker=%s error_type=%s",
                           worker_key, type(exc).__name__)
            _REPORTED_FAILURES.add(worker_key)


def read_worker_health(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must contain a timezone")
    now = now.astimezone(timezone.utc)
    keys = sorted({job.worker_key for job in get_job_catalog()})
    heart = SystemWorkerHeartbeatORM
    ranks = select(
        heart.worker_key, heart.instance_id, heart.last_seen_at,
        heart.poll_interval_seconds, heart.enabled,
        func.row_number().over(
            partition_by=heart.worker_key,
            order_by=(heart.last_seen_at.desc(), heart.instance_id.asc()),
        ).label("position"),
    ).where(heart.worker_key.in_(keys)).subquery()
    observed = db.session.execute(select(
        ranks.c.worker_key, ranks.c.instance_id, ranks.c.last_seen_at,
        ranks.c.poll_interval_seconds, ranks.c.enabled,
    ).where(ranks.c.position <= 8)).all()
    grouped: dict[str, list] = {key: [] for key in keys}
    for row in observed:
        grouped[row.worker_key].append(row)
    states = []
    for key in keys:
        values = grouped[key]
        if not values:
            states.append({
                "worker_key": key, "status": "UNKNOWN",
                "reason_code": "NO_HEARTBEAT",
                "last_seen_at_utc": None, "instance_count": 0,
            })
            continue
        newest = values[0]
        seen = newest.last_seen_at
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
        age = (now - seen.astimezone(timezone.utc)).total_seconds()
        threshold = max(180, 3 * max(10, min(int(newest.poll_interval_seconds), 3600)))
        active = []
        for value in values:
            stamp = value.last_seen_at
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            poll = max(10, min(int(value.poll_interval_seconds), 3600))
            if -30 <= (now - stamp.astimezone(timezone.utc)).total_seconds() <= max(180, 3 * poll):
                active.append(value)
        if age < -30:
            status, reason = "UNKNOWN", "CLOCK_SKEW"
        elif len(active) > 1:
            status, reason = "DEGRADED", "MULTIPLE_ACTIVE_INSTANCES"
        elif age <= threshold and not bool(newest.enabled):
            status, reason = "DISABLED", "WORKER_DISABLED"
        elif age <= threshold:
            status, reason = "HEALTHY", "RECENT_HEARTBEAT"
        elif age <= threshold * 2:
            status, reason = "DEGRADED", "HEARTBEAT_LATE"
        else:
            status, reason = "UNREACHABLE", "HEARTBEAT_EXPIRED"
        states.append({
            "worker_key": key, "status": status, "reason_code": reason,
            "last_seen_at_utc": seen.astimezone(timezone.utc).isoformat(),
            "instance_count": len(active),
        })
    return {
        "workers": states, "checked_at_utc": now.isoformat(),
        "coverage": "PERSISTED_WORKER_HEARTBEATS",
        "note": "Worker liveness only; no job outcome or data-freshness guarantee.",
    }
