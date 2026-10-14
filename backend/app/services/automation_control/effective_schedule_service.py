"""Worker-reported configuration, never a promised run time.

Validates an allowlisted schema at ingestion and again before returning data.
Does not read backend Flask env: only worker process can attest its config.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import and_, func, select

from app.extensions import db
from app.models.automation_control import SystemWorkerHeartbeatORM
from app.services.automation_control.job_catalog import get_job_catalog

_TIME = re.compile(r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
_TZ = re.compile(r"^[A-Za-z0-9_+.-]+(?:/[A-Za-z0-9_+.-]+)*$")
_KINDS = frozenset({
    "DAILY_SLOTS", "DAILY_TIME", "HOURLY_WINDOW", "INTERVAL_CHECK",
    "INTERVAL", "CONDITIONAL", "PENDING_REQUEST", "NIGHTLY_WINDOW",
})


def schedule_spec(*, enabled: bool, timezone_name: str, kind: str,
                  slots: tuple[str, ...] | list[str] = (),
                  conditional: bool = False,
                  interval_seconds: int | None = None) -> dict:
    """Build serializable typed evidence from the worker's resolved settings."""
    return {
        "enabled": enabled, "timezone": timezone_name, "kind": kind,
        "slots": list(slots), "conditional": conditional,
        "interval_seconds": interval_seconds,
    }


def validate_schedule_snapshot(worker_key: str, source: object) -> dict:
    valid_keys = {job.key for job in get_job_catalog() if job.worker_key == worker_key}
    if not isinstance(source, dict) or len(source) > len(valid_keys):
        raise ValueError("Schedule snapshot is not a bounded job mapping")
    accepted = {}
    for job_key, item in source.items():
        if job_key not in valid_keys or not isinstance(item, dict):
            raise ValueError("Unknown job or schedule object")
        if set(item) != {"enabled", "timezone", "kind", "slots",
                         "conditional", "interval_seconds"}:
            raise ValueError("Schedule has unexpected fields")
        enabled, tz, kind = item["enabled"], item["timezone"], item["kind"]
        slots, conditional, interval = (
            item["slots"], item["conditional"], item["interval_seconds"]
        )
        if type(enabled) is not bool or type(conditional) is not bool:
            raise ValueError("Schedule flags must be booleans")
        if (not isinstance(tz, str) or len(tz) > 64 or
                not _TZ.fullmatch(tz) or type(kind) is not str or kind not in _KINDS):
            raise ValueError("Schedule type/timezone invalid")
        if (not isinstance(slots, list) or len(slots) > 24 or
                any(not isinstance(v, str) or not _TIME.fullmatch(v) for v in slots) or
                len(slots) != len(set(slots)) or slots != sorted(slots)):
            raise ValueError("Invalid slot list")
        if interval is not None and (
            type(interval) is not int or not 1 <= interval <= 86400
        ):
            raise ValueError("Interval outside supported bounds")
        if kind in {"DAILY_SLOTS", "DAILY_TIME", "HOURLY_WINDOW"} and enabled and not slots:
            raise ValueError("Enabled scheduled job requires valid slots")
        if kind == "INTERVAL" and enabled and interval is None:
            raise ValueError("Enabled interval job requires interval")
        accepted[job_key] = {
            "enabled": enabled, "timezone": tz, "kind": kind, "slots": slots,
            "conditional": conditional, "interval_seconds": interval,
        }
    return accepted


def read_effective_schedules(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be UTC-aware")
    from app.services.automation_control.worker_health_service import read_worker_health

    health = read_worker_health(now)
    states = {item["worker_key"]: item for item in health["workers"]}
    keys = tuple(states)
    # At most 8 instances per worker; deterministic ordering and no 26-branch N+1.
    table = SystemWorkerHeartbeatORM
    rank = select(
        table.worker_key, table.instance_id,
        func.row_number().over(
            partition_by=table.worker_key,
            order_by=(table.last_seen_at.desc(), table.instance_id.asc()),
        ).label("position"),
    ).where(table.worker_key.in_(keys)).subquery()
    # Return <= one ORM record per worker even after thousands of restarts.
    rows = db.session.execute(
        select(table).join(
            rank, and_(table.worker_key == rank.c.worker_key,
                       table.instance_id == rank.c.instance_id),
        ).where(rank.c.position == 1)
    ).scalars().all()
    first_by_worker = {}
    for row in rows:
        first_by_worker.setdefault(row.worker_key, row)
    jobs = []
    for job in get_job_catalog():
        worker = states[job.worker_key]
        state = "UNVERIFIED"
        spec = None
        reason = "NO_ATTESTED_SCHEDULE"
        if worker["status"] not in {"HEALTHY", "DISABLED"} or worker["instance_count"] != 1:
            reason = "WORKER_HEALTH_NOT_VERIFIED"
        else:
            record = first_by_worker.get(job.worker_key)
            if record is not None and record.job_schedules is not None:
                try:
                    payload = validate_schedule_snapshot(job.worker_key, record.job_schedules)
                except (TypeError, ValueError):
                    reason = "INVALID_SCHEDULE_SNAPSHOT"
                else:
                    value = payload.get(job.key)
                    if value:
                        spec = value
                        state = "DISABLED" if not value["enabled"] else "REPORTED"
                        reason = "WORKER_REPORTED_CONFIG"
        jobs.append({
            "job_key": job.key, "worker_key": job.worker_key,
            "state": state, "reason_code": reason,
            "schedule": spec, "source": "WORKER_HEARTBEAT" if spec else None,
            # A nominal slot can be gated, retried, skipped or blocked by Track.
            "next_due_at": None,
        })
    return {
        "checked_at_utc": health["checked_at_utc"],
        "jobs": jobs,
        "timezone_note": "Resolved timezone belongs to the worker process.",
    }
