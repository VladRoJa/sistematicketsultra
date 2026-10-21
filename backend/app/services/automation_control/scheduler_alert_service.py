"""Conservative, bounded incident summary for ADMICORP's floating alert.

Only persisted evidence is considered. This is not a promise that all jobs
are instrumented or that a nominally scheduled job necessarily ran.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.automation_control.gasca_sms_pulse_service import read_pulse_health
from app.services.automation_control.job_catalog import get_job_catalog
from app.services.automation_control.job_read_service import (
    has_completion_marker_source,
    has_run_source,
    list_job_runs,
)
from app.services.automation_control.worker_health_service import read_worker_health

RECENT_FAILURE_WINDOW = timedelta(hours=36)
FAILURE_STATUSES = frozenset({"FAILED", "ERROR", "FAILURE"})
DEGRADED_STATUSES = frozenset({"PARTIAL", "PARTIAL_FAILED", "COMPLETED_WITH_ERRORS"})
WORKER_CRITICAL = frozenset({"UNREACHABLE"})
WORKER_WARNING = frozenset({"DEGRADED"})


def _utc_now(now: datetime | None) -> datetime:
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return stamp.astimezone(timezone.utc)


def _recent_timestamp(row: dict, now: datetime) -> str | None:
    # Dates are from persisted run evidence, never from frontend clocks.
    for field in ("finished_at_utc", "observed_at_utc", "started_at_utc"):
        value = row.get(field)
        if not value:
            continue
        try:
            stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError, AttributeError):
            continue
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            continue
        elapsed = now - stamp.astimezone(timezone.utc)
        if timedelta(0) <= elapsed <= RECENT_FAILURE_WINDOW:
            return stamp.astimezone(timezone.utc).isoformat()
        return None
    return None


def read_scheduler_alert_summary(now: datetime | None = None) -> dict:
    """Aggregate current worker/pulse states and the latest observed job outcome.

    A historical failed SMS customer request is not scheduler evidence;
    the synthetic SMS pulse covers sender capability independently.
    Completion-only audits cannot demonstrate the absence of failures.
    """
    stamp = _utc_now(now)
    health = read_worker_health(now=stamp)
    pulse = read_pulse_health(now=stamp)
    issues: list[dict] = []

    for worker in health["workers"]:
        status = worker["status"]
        if status in WORKER_CRITICAL | WORKER_WARNING:
            issues.append({
                "key": "worker:" + worker["worker_key"],
                "kind": "WORKER",
                "label": worker["worker_key"],
                "severity": "CRITICAL" if status in WORKER_CRITICAL else "WARNING",
                "reason_code": worker["reason_code"],
                "observed_at_utc": worker.get("last_seen_at_utc"),
            })

    if pulse["state"] in {"FAILED", "LATE"}:
        issues.append({
            "key": "pulse:gasca_sms",
            "kind": "SMS_PULSE",
            "label": "Pulso SMS Gasca",
            "severity": "CRITICAL" if pulse["state"] == "FAILED" else "WARNING",
            "reason_code": "PULSE_" + pulse["state"],
            "observed_at_utc": pulse.get("last_attempt_at_utc"),
        })

    job_count = 0
    for job in get_job_catalog():
        if not has_run_source(job.key) or has_completion_marker_source(job.key):
            continue
        if job.key == "gasca.sms_dispatch":
            # Historic individual customer errors are not scheduler outages.
            continue
        job_count += 1
        data = list_job_runs(job.key, limit=1, offset=0)
        rows = data.get("rows") or []
        if not rows:
            continue
        last = rows[0]
        status = str(last.get("status_raw") or "").strip().upper()
        if status not in FAILURE_STATUSES | DEGRADED_STATUSES:
            continue
        observed_at = _recent_timestamp(last, stamp)
        if observed_at is None:
            continue
        issues.append({
            "key": "job:" + job.key,
            "kind": "JOB_RUN",
            "label": job.label,
            "severity": "CRITICAL" if status in FAILURE_STATUSES else "WARNING",
            "reason_code": "LATEST_RUN_" + status,
            "observed_at_utc": observed_at,
        })

    critical = sum(1 for issue in issues if issue["severity"] == "CRITICAL")
    warning = len(issues) - critical
    return {
        "checked_at_utc": stamp.isoformat(),
        "state": "CRITICAL" if critical else "WARNING" if warning else "CLEAR",
        "issue_count": len(issues),
        "critical_count": critical,
        "warning_count": warning,
        "issues": issues,
        "coverage": "OBSERVED_WORKERS_SMS_PULSE_AND_LATEST_INSTRUMENTED_RUNS",
        "checked_worker_count": len(health["workers"]),
        "checked_run_job_count": job_count,
        "limitations": "UNKNOWN and disabled workers do not imply failure. "
                       "Only the latest instrumented job run in 36h is considered.",
    }
