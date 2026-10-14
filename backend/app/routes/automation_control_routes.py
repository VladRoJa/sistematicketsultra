"""Endpoints M1-B: solo lectura, autorización técnica explícita."""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from app.services.automation_control.timeline_service import daily_timeline
from app.services.automation_control.freshness_service import read_freshness
from app.services.marketing_access import resolve_marketing_access, MarketingAuthorizationError
from app.services.automation_control.worker_health_service import read_worker_health
from app.services.automation_control.effective_schedule_service import read_effective_schedules
from app.services.automation_control.diagnostic_service import (
    run_diagnostic, last_error_diagnostic,
)

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.models.user_model import UserORM
from app.services.automation_control.job_catalog import (
    get_dataset_catalog,
    get_job_catalog,
)
from app.services.automation_control.job_read_service import (
    has_run_source,
    has_completion_marker_source,
    list_job_runs,
)
from app.utils.automation_control_access import can_read_automation_control, can_read_automation_logs


automation_control_bp = Blueprint("automation_control", __name__)


def _require_read_access() -> bool:
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError):
        return False
    user = UserORM.get_by_id(user_id)
    return can_read_automation_control(user)


def _require_log_access() -> bool:
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError):
        return False
    return can_read_automation_logs(UserORM.get_by_id(user_id))


def _deny():
    return jsonify({
        "status": "error",
        "message": "No autorizado para Control de Automatizaciones.",
    }), 403


def _job_metadata(job) -> dict:
    result = asdict(job)
    # Dejar claro que el horario es de REFERENCIA y no la config activa.
    result.update({
        "schedule_source": "CODE_REFERENCE",
        "effective_enabled": None,
        "worker_health": "UNKNOWN",
        "data_freshness": "UNKNOWN",
        "run_history_coverage": (
            "COMPLETION_MARKERS_ONLY"
            if has_completion_marker_source(job.key)
            else "DOMAIN_RUNS" if has_run_source(job.key)
            else "NOT_INSTRUMENTED"
        ),
    })
    return result


def _parse_pagination() -> tuple[int, int]:
    try:
        limit = int(request.args.get("limit", "20"))
        offset = int(request.args.get("offset", "0"))
    except (TypeError, ValueError) as exc:
        raise ValueError("limit y offset deben ser enteros.") from exc
    if not (1 <= limit <= 100 and 0 <= offset <= 10000):
        raise ValueError("limit debe estar entre 1 y 100, offset entre 0 y 10000.")
    return limit, offset


@automation_control_bp.get("/freshness")
@jwt_required()
def automation_control_freshness():
    """Domain-authorized public explanation; no global branch leakage."""
    module_key = str(request.args.get("module_key") or "").strip()
    if module_key not in {"marketing.sales_funnel", "track.daily"}:
        return jsonify({"status": "error", "message": "Dataset no registrado."}), 404

    scope_mode = request.args.get("scope_mode", "GLOBAL")
    if scope_mode not in {"GLOBAL", "FILTERED"}:
        return jsonify({"status": "error", "message": "scope_mode inválido."}), 400
    allowed_args = (
        {"module_key", "scope_mode", "month", "cutoff_date"}
        if module_key == "marketing.sales_funnel"
        else {"module_key", "scope_mode", "track_date"}
    )
    if set(request.args) - allowed_args:
        return jsonify({"status": "error", "message": "Parámetros no admitidos."}), 400
    try:
        identity = int(get_jwt_identity())
    except (TypeError, ValueError):
        return _deny()
    user = UserORM.get_by_id(identity)
    if user is None:
        return _deny()

    if module_key == "marketing.sales_funnel":
        try:
            resolve_marketing_access(user)
        except MarketingAuthorizationError:
            return _deny()
    else:
        allowed_track_roles = {
            "ADMIN", "ADMINISTRADOR", "SUPER_ADMIN", "LECTOR_GLOBAL",
            "GERENTE", "GERENTE_REGIONAL", "SISTEMAS",
            "GERENCIA DEPORTIVA", "MARKETING", "TIENDA",
        }
        if str(getattr(user, "rol", "") or "").strip().upper() not in allowed_track_roles:
            return _deny()

    # Until branch completeness is certified, only ADMICORP corporate/global
    # can see global evidence. Other valid viewers receive scope-safe UNKNOWN.
    global_certified = (
        can_read_automation_control(user) and scope_mode == "GLOBAL"
    )
    try:
        report = read_freshness(
            module_key, scope_global_certified=global_certified,
            month=request.args.get("month"),
            cutoff_date=request.args.get("cutoff_date"),
            track_date=request.args.get("track_date"),
        )
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:
        current_app.logger.exception("Error leyendo frescura. module=%s", module_key)
        return jsonify({
            "status": "error",
            "message": "No fue posible verificar frescura de datos.",
        }), 503

    return jsonify({"status": "ok", **report})


@automation_control_bp.get("/summary")
@jwt_required()
def automation_control_summary():
    if not _require_read_access():
        return _deny()

    jobs = get_job_catalog()
    return jsonify({
        "status": "ok",
        "worker_count": len({job.worker_key for job in jobs}),
        "job_count": len(jobs),
        "dataset_count": len(get_dataset_catalog()),
        "worker_health": "UNKNOWN",
        "effective_schedule_verified": False,
        "runtime_health_instrumented": False,
        "manual_actions_enabled": False,
    })


@automation_control_bp.get("/jobs")
@jwt_required()
def automation_control_jobs():
    if not _require_read_access():
        return _deny()

    domain = str(request.args.get("domain", "")).strip().lower()
    jobs = [
        _job_metadata(job)
        for job in get_job_catalog()
        if not domain or job.domain == domain
    ]
    return jsonify({"status": "ok", "count": len(jobs), "jobs": jobs})


@automation_control_bp.get("/datasets")
@jwt_required()
def automation_control_datasets():
    if not _require_read_access():
        return _deny()

    return jsonify({
        "status": "ok",
        "datasets": [
            {
                **asdict(dataset),
                "latest_complete_business_date": None,
                "data_freshness": "UNKNOWN",
            }
            for dataset in get_dataset_catalog()
        ],
    })


@automation_control_bp.get("/jobs/<job_key>")
@jwt_required()
def automation_control_job(job_key: str):
    if not _require_read_access():
        return _deny()

    job = next((job for job in get_job_catalog() if job.key == job_key), None)
    if job is None:
        return jsonify({"status": "error", "message": "Job no registrado."}), 404

    return jsonify({"status": "ok", "job": _job_metadata(job)})


@automation_control_bp.get("/jobs/<job_key>/runs")
@jwt_required()
def automation_control_runs(job_key: str):
    if not _require_read_access():
        return _deny()

    if not any(job.key == job_key for job in get_job_catalog()):
        return jsonify({"status": "error", "message": "Job no registrado."}), 404

    try:
        limit, offset = _parse_pagination()
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    try:
        payload = list_job_runs(job_key, limit=limit, offset=offset)
    except Exception:
        current_app.logger.exception(
            "No se pudo consultar historial de automatizaciones. job=%s",
            job_key,
        )
        # Nunca retornar SQL/traces ni hacer fallback a un SUCCESS sintético.
        return jsonify({
            "status": "error",
            "message": "No se pudo consultar el historial del job.",
        }), 500

    return jsonify({"status": "ok", "job_key": job_key, **payload})

@automation_control_bp.get("/timeline")
@jwt_required()
def automation_control_timeline():
    if not _require_read_access():
        return _deny()
    raw = request.args.get("date", "")
    try:
        day = date.fromisoformat(raw) if raw else datetime.now(
            ZoneInfo("America/Tijuana")
        ).date()
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Fecha inválida."}), 400
    today = datetime.now(ZoneInfo("America/Tijuana")).date()
    if day > today or day < today - timedelta(days=730):
        return jsonify({"status": "error", "message": "Fecha fuera de rango."}), 400
    try:
        return jsonify({"status": "ok", **daily_timeline(day)})
    except Exception:
        current_app.logger.exception("Fallo al consultar matriz de automatizaciones")
        return jsonify({"status": "error", "message": "No se pudo consultar la matriz."}), 500


@automation_control_bp.get("/jobs/<job_key>/runs/<int:run_id>/diagnostic")
@jwt_required()
def automation_control_run_diagnostic(job_key: str, run_id: int):
    # AUTOMATIONS_LOG_READ (M1): autorización explícita solo ADMICORP.
    if not _require_log_access():
        return _deny()
    if not any(job.key == job_key for job in get_job_catalog()):
        return jsonify({"status": "error", "message": "Job no registrado."}), 404
    try:
        detail = run_diagnostic(job_key, run_id)
    except Exception:
        current_app.logger.exception("Error de consulta diagnóstica. job=%s", job_key)
        return jsonify({"status": "error", "message": "No se pudo consultar el diagnóstico."}), 500
    if detail is None:
        return jsonify({"status": "error", "message": "Ejecución no atribuible al job."}), 404
    current_app.logger.info(
        "AUTOMATION_DIAGNOSTIC_READ actor=%s job=%s run=%s",
        get_jwt_identity(), job_key, run_id,
    )
    return jsonify({"status": "ok", "diagnostic": detail})


@automation_control_bp.get("/jobs/<job_key>/last-error")
@jwt_required()
def automation_control_last_error(job_key: str):
    if not _require_log_access():
        return _deny()
    if not any(job.key == job_key for job in get_job_catalog()):
        return jsonify({"status": "error", "message": "Job no registrado."}), 404
    if request.args.get("scope_key") is not None:
        return jsonify({"status": "error", "message": "Scope técnico no soportado."}), 400
    raw_date = request.args.get("business_date")
    try:
        business_date = date.fromisoformat(raw_date) if raw_date else None
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Fecha inválida."}), 400
    if business_date is not None:
        today = datetime.now(ZoneInfo("America/Tijuana")).date()
        if business_date > today or business_date < today - timedelta(days=730):
            return jsonify({"status": "error", "message": "Fecha fuera de rango."}), 400
    try:
        detail = last_error_diagnostic(job_key, business_date=business_date)
    except Exception:
        current_app.logger.exception("Fallo de lectura último error. job=%s", job_key)
        return jsonify({"status": "error", "message": "No se pudo consultar el diagnóstico."}), 500
    current_app.logger.info(
        "AUTOMATION_LAST_ERROR_READ actor=%s job=%s",
        get_jwt_identity(), job_key,
    )
    return jsonify({"status": "ok", "diagnostic": detail})


@automation_control_bp.get("/workers/health")
@jwt_required()
def automation_control_worker_health():
    if not _require_read_access():
        return _deny()
    try:
        return jsonify({"status": "ok", **read_worker_health()})
    except Exception:
        current_app.logger.exception("Fallo de lectura de salud de workers")
        return jsonify({
            "status": "error",
            "message": "No se pudo verificar la salud de los workers.",
        }), 503


@automation_control_bp.get("/jobs/effective-schedules")
@jwt_required()
def automation_control_effective_schedules():
    if not _require_read_access():
        return _deny()
    try:
        return jsonify({"status": "ok", **read_effective_schedules()})
    except Exception:
        current_app.logger.exception("No se pudo consultar configuración efectiva de workers")
        return jsonify({
            "status": "error",
            "message": "No se pudo verificar la programación efectiva.",
        }), 503
