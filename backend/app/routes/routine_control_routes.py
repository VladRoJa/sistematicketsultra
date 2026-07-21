from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app, jsonify, request, send_file
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.extensions import db
from app.models.user_model import UserORM
from app.routine_control.queries import (
    RoutineControlAuthorizationError,
    RoutineControlOperationalRepository,
    RoutineControlOperationalService,
    RoutineControlValidationError,
    build_members_export,
)


routine_control_bp = Blueprint("routine_control", __name__)


def _current_user() -> UserORM | None:
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError):
        return None
    return db.session.get(UserORM, user_id)


def _service() -> RoutineControlOperationalService:
    return RoutineControlOperationalService(
        RoutineControlOperationalRepository(db.session)
    )


def _error_response(exc: Exception):
    if isinstance(exc, RoutineControlAuthorizationError):
        return jsonify({"error": "Forbidden", "detail": str(exc)}), 403
    if isinstance(exc, RoutineControlValidationError):
        return jsonify({"error": "Bad Request", "detail": str(exc)}), 400
    current_app.logger.exception("Error en consulta operativa de Control de Rutinas")
    return jsonify({
        "error": "Internal Server Error",
        "detail": "No se pudo completar la consulta de Control de Rutinas.",
    }), 500


@routine_control_bp.get("/catalogs")
@jwt_required()
def routine_control_catalogs():
    try:
        return jsonify(_service().catalogs(_current_user())), 200
    except Exception as exc:
        return _error_response(exc)


@routine_control_bp.get("/summary")
@jwt_required()
def routine_control_summary():
    try:
        return jsonify(_service().summary(_current_user(), request.args)), 200
    except Exception as exc:
        return _error_response(exc)


@routine_control_bp.get("/members")
@jwt_required()
def routine_control_members():
    try:
        return jsonify(_service().members(_current_user(), request.args)), 200
    except Exception as exc:
        return _error_response(exc)


@routine_control_bp.get("/members/<int:member_id>")
@jwt_required()
def routine_control_member_detail(member_id: int):
    try:
        detail = _service().member_detail(_current_user(), member_id)
        if detail is None:
            return jsonify({"error": "Not Found", "detail": "Socio no encontrado."}), 404
        return jsonify(detail), 200
    except Exception as exc:
        return _error_response(exc)


@routine_control_bp.get("/runs")
@jwt_required()
def routine_control_runs():
    try:
        return jsonify(_service().runs(_current_user(), request.args)), 200
    except Exception as exc:
        return _error_response(exc)


@routine_control_bp.get("/members/export")
@jwt_required()
def routine_control_members_export():
    try:
        export_limit = int(current_app.config.get("ROUTINE_CONTROL_EXPORT_MAX_ROWS", 10000))
        result = _service().members(
            _current_user(),
            request.args,
            paginate=False,
            row_limit=export_limit + 1,
        )
        if result["total"] > export_limit:
            return jsonify({
                "error": "Payload Too Large",
                "detail": f"La exportación excede el límite de {export_limit} filas. Ajusta los filtros.",
            }), 413
        output = build_members_export(result["items"])
        stamp = datetime.now(ZoneInfo("America/Tijuana")).strftime("%Y%m%d_%H%M%S")
        return send_file(
            output,
            as_attachment=True,
            download_name=f"control_rutinas_{stamp}.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as exc:
        return _error_response(exc)
