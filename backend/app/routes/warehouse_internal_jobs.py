# backend/app/routes/warehouse_internal_jobs.py

from __future__ import annotations

from dataclasses import asdict, dataclass
from http import HTTPStatus
from typing import Any

from flask import Blueprint, current_app, jsonify, request


warehouse_internal_jobs_bp = Blueprint(
    "warehouse_internal_jobs",
    __name__,
    url_prefix="/api/warehouse/internal",
)


SUPPORTED_REPORT_TYPES = frozenset(
    {
        "reporte_direccion",
        "kpi_desempeno",
        "kpi_ventas_nuevos_socios",
    }
)

SUPPORTED_RUN_MODES = frozenset(
    {
        "scheduled_daily",
        "scheduled_month_end_close",
        "manual_backfill",
        "manual_retry",
    }
)

# Qué run_mode acepta cada report_type_key.
RUN_MODE_COMPATIBILITY: dict[str, set[str]] = {
    "reporte_direccion": {
        "scheduled_daily",
        "scheduled_month_end_close",
        "manual_backfill",
        "manual_retry",
    },
    "kpi_desempeno": {
        "scheduled_daily",
        "manual_backfill",
        "manual_retry",
    },
    "kpi_ventas_nuevos_socios": {
        "scheduled_daily",
        "manual_backfill",
        "manual_retry",
    },
}

# Cómo se traduce el run_mode a snapshot_kind.
# Ojo: scheduled_month_end_close solo es válido para reporte_direccion,
# esa regla se valida antes de resolver el snapshot_kind.
SNAPSHOT_KIND_BY_RUN_MODE: dict[str, str] = {
    "scheduled_daily": "daily",
    "scheduled_month_end_close": "month_end_close",
    "manual_backfill": "daily",
    "manual_retry": "daily",
}


@dataclass(slots=True)
class GascaReportJobRequest:
    report_type_key: str
    run_mode: str
    requested_by: str | None
    trigger_source: str | None
    force_ingestion: bool
    snapshot_kind: str


def _json_error(
    message: str,
    status_code: int,
    *,
    code: str,
    details: dict[str, Any] | None = None,
):
    payload: dict[str, Any] = {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
        },
    }

    if details:
        payload["error"]["details"] = details

    return jsonify(payload), status_code


def _normalize_str(value: Any) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        return None

    normalized = value.strip()
    return normalized or None


def _parse_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y", "si", "sí"}:
            return True
        if lowered in {"false", "0", "no", "n"}:
            return False

    if isinstance(value, (int, float)):
        return bool(value)

    return default


def _validate_payload(payload: dict[str, Any]) -> GascaReportJobRequest:
    report_type_key = _normalize_str(payload.get("report_type_key"))
    run_mode = _normalize_str(payload.get("run_mode"))
    requested_by = _normalize_str(payload.get("requested_by"))
    trigger_source = _normalize_str(payload.get("trigger_source"))
    force_ingestion = _parse_bool(payload.get("force_ingestion"), default=True)

    if not report_type_key:
        raise ValueError("El campo 'report_type_key' es obligatorio.")

    if report_type_key not in SUPPORTED_REPORT_TYPES:
        raise ValueError(
            "El 'report_type_key' no es válido. "
            f"Permitidos: {sorted(SUPPORTED_REPORT_TYPES)}"
        )

    if not run_mode:
        raise ValueError("El campo 'run_mode' es obligatorio.")

    if run_mode not in SUPPORTED_RUN_MODES:
        raise ValueError(
            "El 'run_mode' no es válido. "
            f"Permitidos: {sorted(SUPPORTED_RUN_MODES)}"
        )

    allowed_run_modes = RUN_MODE_COMPATIBILITY[report_type_key]
    if run_mode not in allowed_run_modes:
        raise ValueError(
            "La combinación de 'report_type_key' y 'run_mode' no está permitida."
        )

    snapshot_kind = SNAPSHOT_KIND_BY_RUN_MODE[run_mode]

    return GascaReportJobRequest(
        report_type_key=report_type_key,
        run_mode=run_mode,
        requested_by=requested_by,
        trigger_source=trigger_source,
        force_ingestion=force_ingestion,
        snapshot_kind=snapshot_kind,
    )


def _call_orchestrator(job_request: GascaReportJobRequest) -> dict[str, Any]:
    """
    Este wrapper deja el route limpio y evita meter lógica de negocio aquí.

    El archivo del orquestador lo vamos a crear en el siguiente paso:
    backend/app/warehouse/services/gasca_job_orchestrator.py
    función: run_gasca_report_job(...)
    """
    from app.warehouse.services.gasca_job_orchestrator import run_gasca_report_job

    return run_gasca_report_job(
        report_type_key=job_request.report_type_key,
        run_mode=job_request.run_mode,
        snapshot_kind=job_request.snapshot_kind,
        requested_by=job_request.requested_by,
        trigger_source=job_request.trigger_source,
        force_ingestion=job_request.force_ingestion,
    )


@warehouse_internal_jobs_bp.post("/gasca-report-jobs")
def create_gasca_report_job():
    """
    Endpoint interno para disparar una corrida del productor Gasca y, si aplica,
    continuar con upload documental + ingesta estructurada.

    Contrato esperado de entrada:
    {
      "report_type_key": "reporte_direccion",
      "run_mode": "scheduled_daily",
      "requested_by": "system",
      "trigger_source": "scheduler",
      "force_ingestion": true
    }

    Reglas cerradas:
    - reporte_direccion acepta scheduled_month_end_close
    - kpi_desempeno y kpi_ventas_nuevos_socios no aceptan scheduled_month_end_close
    - snapshot_kind se resuelve aquí, no en parser ni en el servicio de ingesta
    """
    payload = request.get_json(silent=True)

    if payload is None:
        return _json_error(
            "Se esperaba un body JSON válido.",
            HTTPStatus.BAD_REQUEST,
            code="INVALID_JSON_BODY",
        )

    if not isinstance(payload, dict):
        return _json_error(
            "El body JSON debe ser un objeto.",
            HTTPStatus.BAD_REQUEST,
            code="INVALID_JSON_OBJECT",
        )

    try:
        job_request = _validate_payload(payload)
    except ValueError as exc:
        return _json_error(
            str(exc),
            HTTPStatus.BAD_REQUEST,
            code="INVALID_JOB_REQUEST",
        )

    current_app.logger.info(
        "Warehouse internal Gasca job requested: report_type_key=%s run_mode=%s "
        "snapshot_kind=%s trigger_source=%s force_ingestion=%s",
        job_request.report_type_key,
        job_request.run_mode,
        job_request.snapshot_kind,
        job_request.trigger_source,
        job_request.force_ingestion,
    )

    try:
        orchestrator_result = _call_orchestrator(job_request)
    except ModuleNotFoundError:
        current_app.logger.exception(
            "No se encontró el módulo del orquestador de Gasca."
        )
        return _json_error(
            "El orquestador de Gasca todavía no está disponible en backend.",
            HTTPStatus.INTERNAL_SERVER_ERROR,
            code="GASCA_ORCHESTRATOR_MODULE_NOT_FOUND",
        )
    except NotImplementedError as exc:
        current_app.logger.exception("Orquestador Gasca no implementado.")
        return _json_error(
            str(exc) or "El orquestador de Gasca aún no está implementado.",
            HTTPStatus.INTERNAL_SERVER_ERROR,
            code="GASCA_ORCHESTRATOR_NOT_IMPLEMENTED",
        )
    except ValueError as exc:
        current_app.logger.warning(
            "Gasca job rechazado por validación de negocio: %s", exc
        )
        return _json_error(
            str(exc),
            HTTPStatus.BAD_REQUEST,
            code="GASCA_JOB_VALIDATION_ERROR",
        )
    except Exception as exc:  # pragma: no cover
        current_app.logger.exception("Fallo no controlado ejecutando Gasca job.")
        return _json_error(
            "Ocurrió un error inesperado al ejecutar el job interno de Gasca.",
            HTTPStatus.INTERNAL_SERVER_ERROR,
            code="GASCA_JOB_EXECUTION_ERROR",
            details={"exception_type": type(exc).__name__},
        )

    response_payload = {
        "ok": True,
        "data": {
            "request": asdict(job_request),
            "result": orchestrator_result,
        },
    }

    return jsonify(response_payload), HTTPStatus.OK