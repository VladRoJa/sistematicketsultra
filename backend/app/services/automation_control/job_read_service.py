"""Lecturas acotadas de ejecuciones reales para el piloto Marketing/Track.

NO infiere el estado del worker, un corte completo, ni un SLA.
Los errores textuales nunca se devuelven: diagnóstico seguro queda para M1-E.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from app.models.attendance import WarehouseAttendanceRunORM
from app.models.marketing import MarketingIventasSyncRunORM, MarketingMetaSyncRunORM
from app.models.routine_control import RoutineControlPipelineRunORM
from sqlalchemy import func
from app.models.warehouse import TrackDailyVersionORM, WarehouseAuditLogORM


# Los demás jobs del catálogo son visibles, pero aún NO cuentan con
# correlación suficiente de corridas para declarar historial instrumentado.
_RUN_SOURCES: dict[str, tuple[type, str | None]] = {
    "marketing.iventas_sync": (MarketingIventasSyncRunORM, None),
    "marketing.meta_sync": (MarketingMetaSyncRunORM, None),
    "reports.attendance_daily_capture": (
        WarehouseAttendanceRunORM, "REPORTS_SCHEDULER",
    ),
    "reports.reactivation_sources_daily": (
        WarehouseAuditLogORM, "reactivation_sources_daily",
    ),
    "reports.reactivation_outcomes_daily": (
        WarehouseAuditLogORM, "reactivation_outcomes_daily",
    ),
    "reports.cobranza_recurrente_rechazados": (
        WarehouseAuditLogORM, "cobranza_recurrente_rechazados",
    ),
    "reports.commercial_daily_reports": (
        WarehouseAuditLogORM, "commercial_daily_reports",
    ),
    "routine_control.scheduled_pipeline": (
        RoutineControlPipelineRunORM, "ROUTINE_CONTROL_SCHEDULER_",
    ),
    "track.preview_operativo": (
        TrackDailyVersionORM, "scheduler_hourly_preview",
    ),
    "track.base_nocturna_canonica": (
        TrackDailyVersionORM, "scheduler_nightly_base",
    ),
    "track.base_nocturna_retry": (
        TrackDailyVersionORM, "scheduler_nightly_retry",
    ),
    "track.request_cierre_canonico": (
        TrackDailyVersionORM, "scheduler_auto_canonical_close",
    ),
}


def has_run_source(job_key: str) -> bool:
    return job_key in _RUN_SOURCES


def has_completion_marker_source(job_key: str) -> bool:
    source = _RUN_SOURCES.get(job_key)
    return source is not None and source[0] is WarehouseAuditLogORM


def _utc_iso(value: datetime | None) -> str | None:
    if value is None or value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def _date_iso(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _serialize_sync_run(row: Any, *, is_meta: bool) -> dict[str, Any]:
    counters = (
        {
            "accounts_requested": int(row.accounts_requested or 0),
            "accounts_completed": int(row.accounts_completed or 0),
            "accounts_failed": int(row.accounts_failed or 0),
        }
        if is_meta
        else {
            "branches_requested": int(row.branches_requested or 0),
            "branches_completed": int(row.branches_completed or 0),
            "branches_failed": int(row.branches_failed or 0),
        }
    )
    return {
        "run_id": int(row.id),
        "business_date": _date_iso(row.date_to),
        "started_at_utc": _utc_iso(row.started_at),
        "finished_at_utc": _utc_iso(row.finished_at),
        "status_raw": str(row.status),
        "is_canonical": bool(row.is_canonical),
        "is_current": None,
        "trigger_source": None,  # No existe en las tablas sync.
        "error_available": False,  # No hay columna de error estructurado.
        "counts": counters,
    }


def _serialize_track_run(row: Any) -> dict[str, Any]:
    return {
        "run_id": int(row.id),
        "business_date": _date_iso(row.track_date),
        "started_at_utc": _utc_iso(row.started_at_utc),
        "finished_at_utc": _utc_iso(row.finished_at_utc),
        "status_raw": str(row.status),
        "is_canonical": None,  # No reemplazar por is_current.
        "is_current": bool(row.is_current),
        "trigger_source": str(row.trigger_source),
        "version_type": str(row.version_type),
        "error_available": bool(row.error_message),
        "counts": {},
    }


def _serialize_attendance_run(row: Any) -> dict[str, Any]:
    """Datos de ejecución exclusivamente; jamás exponer error_message ni source_sha256."""
    return {
        "run_id": int(row.id),
        "business_date": _date_iso(row.business_date),
        "started_at_utc": _utc_iso(row.started_at_utc),
        "finished_at_utc": _utc_iso(row.finished_at_utc),
        "status_raw": str(row.status),
        "is_canonical": None,
        "is_current": None,
        "trigger_source": str(row.trigger_source),
        "error_available": bool(row.error_message),
        "counts": {
            "source_rows": int(row.source_rows or 0),
            "inserted_rows": int(row.inserted_rows or 0),
            "updated_rows": int(row.updated_rows or 0),
            "rejected_rows": int(row.rejected_rows or 0),
        },
    }


AUDIT_COMPLETION_COVERAGE = "COMPLETION_MARKERS_ONLY"


def _filter_reports_completion(query: Any, *, job_key: str) -> Any:
    """Solo marcas de finalización exactas, no uploads ni audits manuales."""
    return query.filter(
        WarehouseAuditLogORM.action == "JOB_COMPLETED",
        WarehouseAuditLogORM.details["source"].as_string() == "reports_scheduler",
        WarehouseAuditLogORM.details["job_key"].as_string() == job_key,
        WarehouseAuditLogORM.details["status"].as_string() == "completed",
    )


def _serialize_reports_completion(row: Any) -> dict[str, Any]:
    """Una marca de auditoría NO acredita duración, inicio ni ausencia de fallos."""
    details = row.details or {}
    raw_date = details.get("business_date")
    try:
        business_date = date.fromisoformat(raw_date).isoformat()
    except (ValueError, TypeError):
        business_date = None
    return {
        "run_id": int(row.id),
        "business_date": business_date,
        "started_at_utc": None,
        "finished_at_utc": None,
        "observed_at_utc": _utc_iso(row.created_at),
        "status_raw": "COMPLETED",
        "evidence_type": "COMPLETION_AUDIT",
        "is_canonical": None,
        "is_current": None,
        "trigger_source": "reports_scheduler",
        "error_available": False,
        "counts": {},
    }


def _filter_routine_scheduler(query: Any) -> Any:
    """Solo runs SCHEDULED con prefijo exacto; nunca MANUAL/BACKFILL/RETRY."""
    prefix = "ROUTINE_CONTROL_SCHEDULER_"
    return query.filter(
        RoutineControlPipelineRunORM.generation_mode == "SCHEDULED",
        func.substr(
            RoutineControlPipelineRunORM.trigger_source, 1, len(prefix),
        ) == prefix,
    )


def _serialize_routine_pipeline_run(row: Any) -> dict[str, Any]:
    """Estado original y métricas; sin errores crudos ni identificadores internos."""
    return {
        "run_id": int(row.id),
        "business_date": _date_iso(row.business_date),
        "started_at_utc": _utc_iso(row.started_at_utc),
        "finished_at_utc": _utc_iso(row.finished_at_utc),
        "observed_at_utc": _utc_iso(row.created_at),
        "status_raw": str(row.status),
        "evidence_type": "PIPELINE_RUN",
        "is_canonical": None,
        "is_current": None,
        "trigger_source": str(row.trigger_source),
        "error_available": bool(row.error_message or row.error_code),
        "counts": {
            "members_created": int(row.members_created or 0),
            "members_updated": int(row.members_updated or 0),
            "incidents_created": int(row.incidents_created or 0),
            "records_rejected": int(row.records_rejected or 0),
        },
    }


def list_job_runs(
    job_key: str, *, limit: int = 20, offset: int = 0
) -> dict[str, Any]:
    """Consulta evidencias por job/trigger, nunca todo el worker como una corrida."""
    if not (1 <= limit <= 100 and 0 <= offset <= 10000):
        raise ValueError("Paginación fuera de rango.")

    source = _RUN_SOURCES.get(job_key)
    if source is None:
        return {
            "coverage": "NOT_INSTRUMENTED",
            "rows": [],
            "has_more": False,
            "limit": limit,
            "offset": offset,
        }

    model, trigger_source = source
    query = model.query
    if model is WarehouseAuditLogORM:
        query = _filter_reports_completion(query, job_key=trigger_source)
    elif model is RoutineControlPipelineRunORM:
        query = _filter_routine_scheduler(query)
    elif trigger_source is not None:
        query = query.filter(model.trigger_source == trigger_source)
    if model is WarehouseAuditLogORM:
        query = query.order_by(model.created_at.desc(), model.id.desc())
        serializer = _serialize_reports_completion
    elif model is RoutineControlPipelineRunORM:
        query = query.order_by(model.created_at.desc(), model.id.desc())
        serializer = _serialize_routine_pipeline_run
    elif model is TrackDailyVersionORM:
        query = query.order_by(model.created_at.desc(), model.id.desc())
        serializer = _serialize_track_run
    elif model is WarehouseAttendanceRunORM:
        query = query.order_by(model.started_at_utc.desc(), model.id.desc())
        serializer = _serialize_attendance_run
    else:
        query = query.order_by(model.started_at.desc(), model.id.desc())
        serializer = lambda row: _serialize_sync_run(
            row, is_meta=job_key == "marketing.meta_sync"
        )

    # +1 determina si hay página siguiente sin COUNT(*) costoso.
    raw_rows = query.offset(offset).limit(limit + 1).all()
    rows = [serializer(row) for row in raw_rows[:limit]]
    return {
        "coverage": (
            AUDIT_COMPLETION_COVERAGE
            if model is WarehouseAuditLogORM else "DOMAIN_RUNS"
        ),
        "rows": rows,
        "has_more": len(raw_rows) > limit,
        "limit": limit,
        "offset": offset,
    }
