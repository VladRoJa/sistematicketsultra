"""Endpoints M1-B: solo lectura, autorización técnica explícita."""
from __future__ import annotations

from dataclasses import asdict

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.models.user_model import UserORM
from app.services.automation_control.job_catalog import (
    get_dataset_catalog,
    get_job_catalog,
)
from app.services.automation_control.job_read_service import (
    has_run_source,
    list_job_runs,
)
from app.utils.automation_control_access import can_read_automation_control


automation_control_bp = Blueprint("automation_control", __name__)


def _require_read_access() -> bool:
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError):
        return False
    user = UserORM.get_by_id(user_id)
    return can_read_automation_control(user)


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
            "DOMAIN_RUNS" if has_run_source(job.key)
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
