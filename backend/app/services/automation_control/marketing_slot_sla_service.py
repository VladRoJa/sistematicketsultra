"""M1-F4: per-slot iVentas/Meta sync freshness, separate from Funnel 5-source SLA.

Read-only. No historical punctuality inference from a monthly snapshot, and
no green unless a current canonical run carries this exact scheduled slot.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.extensions import db
from app.models.marketing import MarketingIventasSyncRunORM, MarketingMetaSyncRunORM
from app.services.automation_control.effective_schedule_service import read_effective_schedules

TZ = ZoneInfo("America/Tijuana")
KEYS = ("marketing.iventas_sync", "marketing.meta_sync")


def marketing_slot_window(*, scheduled_at: datetime, now: datetime) -> dict:
    if any(value.tzinfo is None or value.utcoffset() is None
           for value in (scheduled_at, now)):
        raise ValueError("Fechas SLA deben incluir timezone.")
    slot_utc = scheduled_at.astimezone(timezone.utc)
    due = slot_utc + timedelta(minutes=60)
    late = slot_utc + timedelta(minutes=120)
    checked = now.astimezone(timezone.utc)
    status = ("NOT_DUE" if checked < due else
              "LAGGING" if checked < late else "LATE")
    return {
        "slot_at": slot_utc.astimezone(TZ).isoformat(),
        "due_at": due.astimezone(TZ).isoformat(),
        "late_at": late.astimezone(TZ).isoformat(),
        "phase_if_unavailable": status,
    }


def _unverified(business_date: date, reason: str) -> dict:
    return {
        "business_date": business_date.isoformat(), "status": "UNKNOWN",
        "reason_code": reason, "slot_at": None, "due_at": None,
        "late_at": None, "timezone": TZ.key, "sources": [],
        "scope": "SYNC_ONLY_NOT_FUNNEL_CONSOLIDATED",
    }


def _source_outcome(*, model: type, business_date: date,
                    scheduled_at: datetime, phase: str, key: str) -> dict:
    # Max 20 attempts. A saturated result is unverifiable, never a green.
    rows = (
        db.session.query(model.id, model.status, model.is_canonical, model.finished_at)
        .filter(
            model.scheduler_slot_at == scheduled_at.astimezone(timezone.utc),
            model.date_from == business_date.replace(day=1),
            model.date_to == business_date,
        ).order_by(model.id.desc()).limit(20).all()
    )
    if len(rows) == 20:
        return {"key": key, "status": "UNKNOWN", "reason_code": "ATTEMPTS_LIMIT"}
    canonical = [
        row for row in rows if row[1] == "COMPLETED" and row[2] is True
        and row[3] is not None
    ]
    if len(canonical) > 1:
        return {"key": key, "status": "UNKNOWN", "reason_code": "AMBIGUOUS_CANONICAL"}
    if canonical:
        return {"key": key, "status": "UP_TO_DATE", "reason_code": "SLOT_CURRENT_CANONICAL_SUCCESS"}
    if any(row[1] == "COMPLETED" for row in rows):
        # A superseded run can have been canonical when it finished. The
        # current flag cannot certify historical punctuality.
        return {"key": key, "status": "UNKNOWN", "reason_code": "COMPLETION_NOT_CURRENT"}
    return {"key": key, "status": phase, "reason_code": (
        "SLOT_RUN_INCOMPLETE" if rows else "NO_ATTRIBUTED_SLOT_RUN"
    )}


def read_marketing_sync_sla(*, business_date: date, now: datetime) -> dict:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now debe incluir timezone.")
    local_now = now.astimezone(TZ)
    if business_date != local_now.date():
        return _unverified(business_date, "HISTORICAL_SCHEDULE_NOT_ATTESTED")

    observed = read_effective_schedules(now=now.astimezone(timezone.utc))
    found = {item["job_key"]: item for item in observed["jobs"]
             if item["job_key"] in KEYS}
    if set(found) != set(KEYS):
        return _unverified(business_date, "MISSING_WORKER_SCHEDULE")
    specs = []
    for key in KEYS:
        job = found[key]
        if job["state"] == "DISABLED":
            return _unverified(business_date, "SYNC_DISABLED")
        if job["state"] != "REPORTED":
            return _unverified(business_date, "WORKER_SCHEDULE_UNVERIFIED")
        spec = job.get("schedule")
        if not spec or not spec["enabled"] or spec["timezone"] != TZ.key or spec["kind"] != "DAILY_SLOTS":
            return _unverified(business_date, "SCHEDULE_NOT_TIJUANA_DAILY_SLOTS")
        specs.append(tuple(spec["slots"]))
    if specs[0] != specs[1] or not specs[0]:
        return _unverified(business_date, "SYNC_SLOTS_DIVERGE")

    valid_slots = []
    for slot in specs[0]:
        try:
            hour, minute = (int(x) for x in slot.split(":"))
            local_slot = datetime.combine(business_date, time(hour, minute), tzinfo=TZ)
        except (TypeError, ValueError):
            return _unverified(business_date, "INVALID_EFFECTIVE_SLOT")
        # Reject nonexistent local clock times (DST spring) as unverifiable.
        roundtrip = local_slot.astimezone(timezone.utc).astimezone(TZ)
        if roundtrip.replace(tzinfo=None) != local_slot.replace(tzinfo=None):
            return _unverified(business_date, "NONEXISTENT_LOCAL_SLOT")
        valid_slots.append(local_slot)
    elapsed = [slot for slot in valid_slots if slot.astimezone(timezone.utc) <= now.astimezone(timezone.utc)]
    slot_at = elapsed[-1] if elapsed else valid_slots[0]
    window = marketing_slot_window(scheduled_at=slot_at, now=now)
    sources = [
        _source_outcome(
            model=model, business_date=business_date,
            scheduled_at=slot_at, phase=window["phase_if_unavailable"], key=key,
        ) for key, model in (
            (KEYS[0], MarketingIventasSyncRunORM),
            (KEYS[1], MarketingMetaSyncRunORM),
        )
    ] if elapsed else [
        {"key": key, "status": "NOT_DUE", "reason_code": "FIRST_SLOT_NOT_STARTED"}
        for key in KEYS
    ]

    values = {item["status"] for item in sources}
    status = (
        "UNKNOWN" if "UNKNOWN" in values else
        "LATE" if "LATE" in values else
        "LAGGING" if "LAGGING" in values else
        "UP_TO_DATE" if values == {"UP_TO_DATE"} else
        "NOT_DUE"
    )
    return {
        "business_date": business_date.isoformat(), "status": status,
        "reason_code": "SYNC_SLOT_EVALUATED",
        "slot_at": window["slot_at"], "due_at": window["due_at"],
        "late_at": window["late_at"], "timezone": TZ.key,
        "sources": sources, "scope": "SYNC_ONLY_NOT_FUNNEL_CONSOLIDATED",
    }
