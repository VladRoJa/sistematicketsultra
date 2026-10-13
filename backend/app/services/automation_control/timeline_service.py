"""Vista diaria de evidencia real, sin asignar corridas a slots no persistidos."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.models.marketing import MarketingIventasSyncRunORM, MarketingMetaSyncRunORM
from app.models.warehouse import TrackDailyVersionORM
from app.services.automation_control.job_catalog import get_job_catalog
from app.services.automation_control.job_read_service import (
    _serialize_sync_run, _serialize_track_run,
)

LOCAL_TZ = ZoneInfo("America/Tijuana")
# Inventario de referencia solamente: NO es configuración efectiva.
_REFERENCE = {
    "marketing.iventas_sync": ("08:20", "12:20", "16:20", "20:20"),
    "marketing.meta_sync": ("08:20", "12:20", "16:20", "20:20"),
    "track.preview_operativo": tuple(f"{hour:02d}:00" for hour in range(5, 24)),
    "track.base_nocturna_canonica": ("23:30",),
}
_TRIGGERS = {
    "track.preview_operativo": "scheduler_hourly_preview",
    "track.base_nocturna_canonica": "scheduler_nightly_base",
}
_MODELS = {
    "marketing.iventas_sync": MarketingIventasSyncRunORM,
    "marketing.meta_sync": MarketingMetaSyncRunORM,
    "track.preview_operativo": TrackDailyVersionORM,
    "track.base_nocturna_canonica": TrackDailyVersionORM,
}


def _local_start(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.astimezone(LOCAL_TZ)


def _observations(job_key: str, day: date) -> list[dict]:
    model = _MODELS.get(job_key)
    if model is None:
        return []
    begin = datetime.combine(day, time.min, LOCAL_TZ).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), time.min, LOCAL_TZ).astimezone(timezone.utc)
    stamp = model.started_at_utc if model is TrackDailyVersionORM else model.started_at
    query = model.query.filter(stamp >= begin, stamp < end)
    if model is TrackDailyVersionORM:
        query = query.filter(model.trigger_source == _TRIGGERS[job_key])
    rows = query.order_by(stamp.desc(), model.id.desc()).limit(500).all()
    result = []
    for row in rows:
        local = _local_start(row.started_at_utc if model is TrackDailyVersionORM else row.started_at)
        if local is None or local.date() != day:
            continue
        entry = _serialize_track_run(row) if model is TrackDailyVersionORM else _serialize_sync_run(
            row, is_meta=job_key == "marketing.meta_sync",
        )
        entry["observed_hour"] = local.strftime("%H:00")
        entry["observed_time"] = local.strftime("%H:%M")
        result.append(entry)
    return result


def daily_timeline(day: date) -> dict:
    """Observaciones por hora local; NO infiere que un slot concreto se cumplió."""
    groups: dict[str, list] = {}
    for job in get_job_catalog():
        entries = _observations(job.key, day)
        by_hour: dict[str, list] = {}
        for entry in entries:
            by_hour.setdefault(entry["observed_hour"], []).append(entry)
        groups.setdefault(job.worker_key, []).append({
            "job_key": job.key,
            "label": job.label,
            "schedule_kind": job.schedule_kind,
            "reference_slots": list(_REFERENCE.get(job.key, ())),
            "schedule_verified": False,
            "observed": by_hour,
            "coverage": "OBSERVED_RUNS" if job.key in _MODELS else "NOT_INSTRUMENTED",
        })
    for worker in ("reports-scheduler", "routine-control-scheduler", "ticket-attachment-cleanup"):
        groups.setdefault(worker, [])
    return {"date": day.isoformat(), "timezone": str(LOCAL_TZ),
            "schedule_verified": False, "workers": [
                {"worker_key": worker, "jobs": jobs}
                for worker, jobs in groups.items()
            ]}
