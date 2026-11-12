"""Read-only, attributable observation of independent iVentas cobranza sends.

A scheduler completion audit is NOT evidence of provider acceptance. This
aggregates only branch-specific governance audits and their durable V2 jobs.
No customer identifiers, telephone numbers, raw provider errors or send actions.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func

from app.extensions import db
from app.models.marketing import MarketingCampaignV2ProviderCampaignORM as ProviderBatch
from app.models.marketing_campaign_v2_background_job import (
    MarketingCampaignV2BackgroundJobORM as DispatchJob,
)
from app.models.warehouse import WarehouseAuditLogORM as Audit

JOB_KEY = "reports.cobranza_iventas_multibranch"
AUDIT_ACTION = "COBRANZA_BRANCH_AUTO"
MAX_BRANCHES = 30
MAX_AUDITS_PER_DAY = 500


def _utc_iso(value: datetime | None) -> str | None:
    if value is None or value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def _safe_code(raw: Any) -> str | None:
    """Do not echo arbitrary provider payloads or free-text exceptions."""
    import re
    value = str(raw or "").strip()
    return value if re.fullmatch(r"[A-Z][A-Z0-9_]{1,79}", value) else None


def _audit_day(row: Audit) -> str | None:
    value = (row.details or {}).get("business_date")
    try:
        return date.fromisoformat(value).isoformat()
    except (ValueError, TypeError):
        return None


def _days(*, limit: int, offset: int) -> tuple[list[str], bool]:
    day = Audit.details["business_date"].as_string()
    group = (
        db.session.query(day.label("day"), func.max(Audit.id).label("last_id"))
        .filter(Audit.action == AUDIT_ACTION)
        .group_by(day)
        .order_by(func.max(Audit.id).desc())
        .offset(offset).limit(limit + 1).all()
    )
    found = []
    for item in group:
        try:
            found.append(date.fromisoformat(item.day).isoformat())
        except (ValueError, TypeError):
            continue
    return found[:limit], len(group) > limit


def _branch_state(audit: Audit, jobs: dict[int, Any],
                  batches: dict[int, list[Any]]) -> dict[str, Any]:
    details = audit.details or {}
    branch = str(details.get("branch") or "")
    campaign_id = details.get("campaign_id")
    campaign_id = campaign_id if type(campaign_id) is int and campaign_id > 0 else None
    job = jobs.get(campaign_id)
    provider_rows = batches.get(campaign_id, [])
    raw_job = str(job.status or "") if job is not None else None
    statuses = [str(batch.status or "") for batch in provider_rows]
    reason = _safe_code(details.get("reason"))
    if job is not None:
        reason = _safe_code(job.stop_reason_code) or reason

    if job is None:
        state = "SKIPPED" if details.get("status") == "SKIPPED" else "PENDING"
    elif raw_job in {"QUEUED", "RUNNING", "STOP_REQUESTED"}:
        state = "PENDING"
    elif raw_job == "COMPLETED" and statuses and all(
        status == "SUBMITTED" for status in statuses
    ):
        state = "SUBMITTED"
    else:
        state = "REVIEW_REQUIRED"
        if reason is None:
            reason = "PROVIDER_OR_JOB_REVIEW"

    return {
        "branch": branch,
        "status": state,
        "job_status": raw_job,
        "provider_status": (
            statuses[0] if len(statuses) == 1 else
            "MULTIPLE_BATCHES" if statuses else None
        ),
        "recipients": sum(int(row.recipient_count or 0) for row in provider_rows),
        "reason_code": reason,
    }


def _read_day(day: str) -> dict | None:
    rows = (
        db.session.query(Audit)
        .filter(
            Audit.action == AUDIT_ACTION,
            Audit.details["business_date"].as_string() == day,
        )
        .order_by(Audit.id.desc())
        .limit(MAX_AUDITS_PER_DAY + 1).all()
    )
    if not rows:
        return None
    truncated = len(rows) > MAX_AUDITS_PER_DAY
    rows = rows[:MAX_AUDITS_PER_DAY]
    latest: dict[str, Audit] = {}
    expected = 0
    for row in rows:
        meta = row.details or {}
        branch = meta.get("branch")
        if isinstance(branch, str) and len(branch) <= 100 and branch and branch not in latest:
            latest[branch] = row
        count = meta.get("expected_branches")
        if type(count) is int and 1 <= count <= MAX_BRANCHES:
            expected = max(expected, count)

    campaign_ids = {
        meta["campaign_id"] for row in latest.values()
        if (meta := (row.details or {}))
        if type(meta.get("campaign_id")) is int and meta["campaign_id"] > 0
    }
    jobs: dict[int, Any] = {}
    batches: dict[int, list[Any]] = defaultdict(list)
    if campaign_ids:
        for job in db.session.query(DispatchJob).filter(
            DispatchJob.campaign_v2_id.in_(campaign_ids)
        ).order_by(DispatchJob.id.desc()).all():
            jobs.setdefault(int(job.campaign_v2_id), job)
        for batch in db.session.query(ProviderBatch).filter(
            ProviderBatch.campaign_v2_id.in_(campaign_ids)
        ).all():
            batches[int(batch.campaign_v2_id)].append(batch)

    branches = [
        _branch_state(row, jobs, batches)
        for branch, row in sorted(latest.items())
    ]
    accepted = sum(item["status"] == "SUBMITTED" for item in branches)
    pending = sum(item["status"] == "PENDING" for item in branches)
    review = sum(item["status"] == "REVIEW_REQUIRED" for item in branches)
    skipped = sum(item["status"] == "SKIPPED" for item in branches)
    missing = max(expected - len(branches), 0)
    # Without a durable expected roster we never declare 100% completion.
    if truncated or not expected or missing or review or skipped:
        state = "PARTIAL"
    elif pending:
        state = "RUNNING"
    elif accepted == expected:
        state = "COMPLETED"
    else:
        state = "PARTIAL"

    started = min((row.created_at for row in rows if row.created_at), default=None)
    last_audit = max(rows, key=lambda row: row.id)
    finished = None
    if state == "COMPLETED" and jobs:
        times = [job.finished_at for job in jobs.values()]
        if times and all(times):
            finished = max(times)

    return {
        "run_id": int(last_audit.id),
        "business_date": day,
        "started_at_utc": _utc_iso(started),
        "finished_at_utc": _utc_iso(finished),
        "observed_at_utc": _utc_iso(last_audit.created_at),
        "status_raw": state,
        "evidence_type": "COBRANZA_BRANCH_AUDIT_AND_PROVIDER_JOBS",
        "is_canonical": None,
        "is_current": None,
        "trigger_source": "reports_scheduler",
        "error_available": bool(review or skipped or missing or truncated),
        "counts": {
            "branches_expected": expected or None,
            "branches_observed": len(branches),
            "branches_submitted": accepted,
            "branches_pending": pending,
            "branches_review": review,
            "branches_skipped": skipped,
            "branches_missing": missing,
            "recipients_submitted": sum(
                item["recipients"] for item in branches
                if item["status"] == "SUBMITTED"
            ),
        },
        "branches": branches,
        "evidence_truncated": truncated,
    }


def list_multibranch_runs(*, limit: int, offset: int) -> dict:
    if not 1 <= limit <= 100 or not 0 <= offset <= 10000:
        raise ValueError("Paginación fuera de rango.")
    days, has_more = _days(limit=limit, offset=offset)
    return {
        "coverage": "DOMAIN_RUNS",
        "rows": [result for day in days if (result := _read_day(day))],
        "has_more": has_more,
        "limit": limit,
        "offset": offset,
    }


def _diagnostic(run: dict) -> dict:
    counts = run["counts"]
    failures = [
        {"branch_code": item["branch"],
         "error_type": item["reason_code"] or item["status"]}
        for item in run["branches"]
        if item["status"] in {"SKIPPED", "REVIEW_REQUIRED"}
    ]
    return {
        "job_key": JOB_KEY,
        "run_id": run["run_id"],
        "business_date": run["business_date"],
        "status": run["status_raw"],
        "started_at_utc": run["started_at_utc"],
        "finished_at_utc": run["finished_at_utc"],
        "diagnostic_state": "STRUCTURED_COUNTERS_ONLY",
        "sanitized_message": (
            "Estados observados en auditorías y jobs de iVentas. "
            "SUBMITTED acredita aceptación, no entrega al socio. "
            "Resultados inciertos requieren conciliación antes de reenviar."
        ),
        "log_state": "LOG_NOT_AVAILABLE",
        "log_lines": [],
        "truncated": False,
        "counts": {
            "branches_requested": counts["branches_expected"] or counts["branches_observed"],
            "branches_completed": counts["branches_submitted"],
            "branches_failed": counts["branches_review"] + counts["branches_skipped"] + counts["branches_missing"],
            "aliases_unresolved": 0,
        },
        "branch_failures": failures,
        "failure_details_coverage": "RECORDED_ONLY",
        "failure_details_truncated": run["evidence_truncated"],
    }


def multibranch_run_diagnostic(run_id: int) -> dict | None:
    if type(run_id) is not int or run_id <= 0:
        return None
    audit = db.session.query(Audit).filter(
        Audit.id == run_id, Audit.action == AUDIT_ACTION,
    ).first()
    if audit is None:
        return None
    day = _audit_day(audit)
    return _diagnostic(run) if day and (run := _read_day(day)) else None


def multibranch_last_error(day: date | None = None) -> dict:
    if day is not None:
        dates = [day.isoformat()]
    else:
        dates, _ = _days(limit=60, offset=0)
    for current_day in dates:
        run = _read_day(current_day)
        if run is not None and run["status_raw"] == "PARTIAL":
            return {**_diagnostic(run), "failure_recency": "HISTORICAL_OR_ACTIVE_UNVERIFIED"}
    return {
        "job_key": JOB_KEY, "diagnostic_state": "LOG_NOT_AVAILABLE",
        "sanitized_message": "No existe fallo multicucursal atribuible al corte consultado.",
        "run_id": None, "business_date": day.isoformat() if day else None,
        "log_lines": [], "truncated": False,
    }
