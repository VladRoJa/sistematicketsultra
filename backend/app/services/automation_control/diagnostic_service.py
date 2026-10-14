"""Diagnósticos estrictamente atribuibles: metadatos seguros sin logs crudos.

Ninguna tabla legacy garantiza una bitácora sanitizada por run. Nunca deducir
causas de mensajes libres ni reutilizar fallos de otros jobs/cortes.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.models.attendance import WarehouseAttendanceRunORM
from app.models.marketing import MarketingIventasSyncRunORM, MarketingMetaSyncRunORM, MarketingIventasBranchFailureORM
from app.models.routine_control import RoutineControlPipelineRunORM
from app.models.warehouse import TrackDailyVersionORM, WarehouseAuditLogORM
from app.services.automation_control.job_read_service import (
    _RUN_SOURCES, _date_iso, _filter_reports_completion,
    _filter_routine_scheduler, _utc_iso,
)

FAILED_STATUSES = ("FAILED", "ERROR", "TIMED_OUT", "PARTIAL")


def _attributed_query(job_key: str):
    source = _RUN_SOURCES.get(job_key)
    if source is None:
        return None, None
    model, trigger = source
    if model is WarehouseAuditLogORM:
        # El audit guarda solo completions; jamás adjudicarles fallos.
        return None, None
    query = model.query
    if model is RoutineControlPipelineRunORM:
        query = _filter_routine_scheduler(query)
    elif trigger is not None:
        query = query.filter(model.trigger_source == trigger)
    return model, query


def _date_field(model):
    if model is TrackDailyVersionORM:
        return model.track_date
    if model in (MarketingIventasSyncRunORM, MarketingMetaSyncRunORM):
        return model.date_to
    return model.business_date


def _time_field(model):
    if model is TrackDailyVersionORM:
        return model.created_at
    if model in (MarketingIventasSyncRunORM, MarketingMetaSyncRunORM):
        return model.started_at
    if model is WarehouseAttendanceRunORM:
        return model.started_at_utc
    return model.created_at


def _iventas_structured_summary(row: MarketingIventasSyncRunORM) -> dict:
    """Contadores del MISMO sync_run; no identifican causa ni sucursal específica."""
    counters = {
        "branches_requested": int(row.branches_requested or 0),
        "branches_completed": int(row.branches_completed or 0),
        "branches_failed": int(row.branches_failed or 0),
        "aliases_unresolved": int(row.aliases_unresolved or 0),
    }
    status = str(row.status or "").upper()
    if status == "COMPLETED":
        message = (
            f"Se completaron {counters['branches_completed']} de "
            f"{counters['branches_requested']} sucursales. "
            "La finalización no garantiza la frescura de los datos."
        )
    else:
        message = (
            f"Se completaron {counters['branches_completed']} de "
            f"{counters['branches_requested']} sucursales; "
            f"{counters['branches_failed']} no se completaron y "
            f"{counters['aliases_unresolved']} alias quedaron sin resolver. "
            "Estos son contadores persistidos de la corrida. "
            "No hay causa técnica individual por sucursal registrada."
        )
    return {"counts": counters, "sanitized_message": message}


def _safe_response(job_key: str, row: Any) -> dict:
    status = str(row.status or "").upper()
    date_value = (
        row.track_date if isinstance(row, TrackDailyVersionORM)
        else row.date_to if isinstance(row, (MarketingIventasSyncRunORM, MarketingMetaSyncRunORM))
        else row.business_date
    )
    start = (row.started_at if isinstance(row, (MarketingIventasSyncRunORM, MarketingMetaSyncRunORM))
             else row.started_at_utc)
    finish = (row.finished_at if isinstance(row, (MarketingIventasSyncRunORM, MarketingMetaSyncRunORM))
              else row.finished_at_utc)
    # Error_code y error_message pueden contener información interna o personal.
    # No usamos ninguno en la respuesta. Tampoco hacemos shell/docker logs.
    return {
        "job_key": job_key,
        "run_id": int(row.id),
        "business_date": _date_iso(date_value),
        "status": status,
        "started_at_utc": _utc_iso(start),
        "finished_at_utc": _utc_iso(finish),
        "diagnostic_state": (
            "LOG_NOT_AVAILABLE" if status in FAILED_STATUSES
            else "NOT_APPLICABLE"
        ),
        "error_code": None,
        "log_state": "LOG_NOT_AVAILABLE",
        "sanitized_message": (
            "No hay log sanitizado registrado para esta ejecución."
            if status in FAILED_STATUSES
            else "La ejecución indicada no registra un resultado fallido."
        ),
        "failed_stage": None,
        "correlation_id": None,
        "log_lines": [],
        "truncated": False,
        "source": "LEGACY_RUN_METADATA_ONLY",
    }


def _iventas_failure_details(run_id: int) -> dict:
    """Registros estructurados del run exacto. Nunca acceder a raw_pages."""
    rows = (
        MarketingIventasBranchFailureORM.query
        .filter_by(sync_run_id=run_id)
        .order_by(MarketingIventasBranchFailureORM.branch_code.asc())
        .limit(101)
        .all()
    )
    allowed = frozenset({
        "ALIAS_UNRESOLVED",
        "ALIAS_AMBIGUOUS_DESTINATION",
        "MarketingIventasBranchResolutionError",
        "MarketingIventasBranchSyncError",
        "IventasClientError",
        "UNEXPECTED_BRANCH_ABORT",
    })
    # Capa adicional de defensa aunque la tabla tenga CHECK.
    details = [
        {"branch_code": row.branch_code, "error_type": row.error_type}
        for row in rows[:100]
        if row.error_type in allowed
    ]
    return {
        "branch_failures": details,
        "failure_details_coverage": (
            "RECORDED_ONLY" if details else "NOT_RECORDED"
        ),
        "failure_details_truncated": len(rows) > 100,
    }


def _diagnostic_with_structured_evidence(job_key: str, row: Any) -> dict:
    result = _safe_response(job_key, row)
    if job_key == "marketing.iventas_sync" and isinstance(
        row, MarketingIventasSyncRunORM,
    ):
        result.update(_iventas_structured_summary(row))
        if result["status"] in FAILED_STATUSES:
            result.update(_iventas_failure_details(int(row.id)))
        result["diagnostic_state"] = "STRUCTURED_COUNTERS_ONLY"
        result["source"] = "IVENTAS_RUN_COUNTERS"
    return result


def run_diagnostic(job_key: str, run_id: int) -> dict | None:
    if run_id <= 0:
        return None
    model, query = _attributed_query(job_key)
    if model is None:
        return None
    row = query.filter(model.id == run_id).first()
    if row is None:
        return None
    return _diagnostic_with_structured_evidence(job_key, row)


def last_error_diagnostic(job_key: str, *, business_date: date | None = None) -> dict:
    model, query = _attributed_query(job_key)
    if model is None:
        return {
            "job_key": job_key, "diagnostic_state": "LOG_NOT_AVAILABLE",
            "sanitized_message": "No existe historial de fallos atribuible a este job.",
            "run_id": None, "business_date": (
                business_date.isoformat() if business_date else None
            ),
            "log_lines": [], "truncated": False,
        }
    if business_date is not None:
        query = query.filter(_date_field(model) == business_date)
    status_upper = model.status
    query = query.filter(status_upper.in_(
        ("FAILED", "ERROR", "TIMED_OUT", "PARTIAL", "failed", "error", "timed_out", "partial")
    ))
    row = query.order_by(_time_field(model).desc(), model.id.desc()).first()
    if row is None:
        return {
            "job_key": job_key, "diagnostic_state": "LOG_NOT_AVAILABLE",
            "sanitized_message": "No hay corrida fallida registrada para este job y corte.",
            "run_id": None, "business_date": (
                business_date.isoformat() if business_date else None
            ),
            "log_lines": [], "truncated": False,
        }
    result = _diagnostic_with_structured_evidence(job_key, row)
    # No afirmar fallo activo: la verificación de recuperación exige resolver
    # el orden completo de intentos, slot y scope por dominio.
    result["failure_recency"] = "HISTORICAL_OR_ACTIVE_UNVERIFIED"
    return result
