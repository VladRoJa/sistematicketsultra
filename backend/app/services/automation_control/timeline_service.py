"""Vista diaria de evidencia real, sin asignar corridas a slots no persistidos."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.models.attendance import WarehouseAttendanceRunORM
from app.models.marketing import MarketingIventasSyncRunORM, MarketingMetaSyncRunORM
from app.models.routine_control import RoutineControlPipelineRunORM
from app.models.warehouse import TrackDailyVersionORM, WarehouseAuditLogORM
from app.services.automation_control.job_catalog import get_job_catalog
from app.services.automation_control.job_read_service import (
    _filter_reports_completion, _serialize_reports_completion,
    _filter_routine_scheduler, _serialize_routine_pipeline_run,
    _serialize_attendance_run, _serialize_sync_run, _serialize_track_run,
)

LOCAL_TZ = ZoneInfo("America/Tijuana")
# Inventario de referencia solamente: NO es configuración efectiva.
_REFERENCE = {
    "marketing.iventas_sync": ("08:20", "12:20", "16:20", "20:20"),
    "marketing.meta_sync": ("08:20", "12:20", "16:20", "20:20"),
    "track.preview_operativo": tuple(f"{hour:02d}:00" for hour in range(5, 24)),
    "track.base_nocturna_canonica": ("23:30",),
    "reports.attendance_daily_capture": ("06:20",),
    "reports.reactivation_sources_daily": ("09:00",),
    "reports.reactivation_outcomes_daily": ("09:15",),
    "reports.cobranza_recurrente_rechazados": ("08:00",),
    "routine_control.scheduled_pipeline": ("09:20", "13:20", "17:20", "21:20"),
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
    "reports.attendance_daily_capture": WarehouseAttendanceRunORM,
    "reports.reactivation_sources_daily": WarehouseAuditLogORM,
    "reports.reactivation_outcomes_daily": WarehouseAuditLogORM,
    "reports.cobranza_recurrente_rechazados": WarehouseAuditLogORM,
    "reports.commercial_daily_reports": WarehouseAuditLogORM,
    "routine_control.scheduled_pipeline": RoutineControlPipelineRunORM,
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
    stamp = (
        model.started_at
        if model in (MarketingIventasSyncRunORM, MarketingMetaSyncRunORM)
        else model.created_at if model in (
            WarehouseAuditLogORM, RoutineControlPipelineRunORM,
        )
        else model.started_at_utc
    )
    query = model.query.filter(stamp >= begin, stamp < end)
    if model is WarehouseAuditLogORM:
        query = _filter_reports_completion(
            query, job_key=job_key.removeprefix("reports."),
        )
    elif model is RoutineControlPipelineRunORM:
        query = _filter_routine_scheduler(query)
    elif model is TrackDailyVersionORM:
        query = query.filter(model.trigger_source == _TRIGGERS[job_key])
    elif model is WarehouseAttendanceRunORM:
        query = query.filter(model.trigger_source == "REPORTS_SCHEDULER")
    rows = query.order_by(stamp.desc(), model.id.desc()).limit(500).all()
    result = []
    for row in rows:
        local = _local_start(
            row.started_at if model in (
                MarketingIventasSyncRunORM, MarketingMetaSyncRunORM,
            ) else row.created_at if model in (
                WarehouseAuditLogORM, RoutineControlPipelineRunORM,
            )
            else row.started_at_utc
        )
        if local is None or local.date() != day:
            continue
        if model is WarehouseAuditLogORM:
            entry = _serialize_reports_completion(row)
        elif model is RoutineControlPipelineRunORM:
            entry = _serialize_routine_pipeline_run(row)
        elif model is TrackDailyVersionORM:
            entry = _serialize_track_run(row)
        elif model is WarehouseAttendanceRunORM:
            entry = _serialize_attendance_run(row)
        else:
            entry = _serialize_sync_run(
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
            "coverage": (
                "COMPLETION_MARKERS_ONLY" if _MODELS.get(job.key) is WarehouseAuditLogORM
                else "OBSERVED_RUNS" if job.key in _MODELS
                else "NOT_INSTRUMENTED"
            ),
        })
    for worker in ("reports-scheduler", "routine-control-scheduler", "ticket-attachment-cleanup"):
        groups.setdefault(worker, [])
    return {"date": day.isoformat(), "timezone": str(LOCAL_TZ),
            "schedule_verified": False, "workers": [
                {"worker_key": worker, "jobs": jobs}
                for worker, jobs in groups.items()
            ]}
