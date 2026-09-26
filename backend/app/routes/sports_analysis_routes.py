from __future__ import annotations

from datetime import date

from flask import (
    Blueprint,
    current_app,
    jsonify,
    request,
)
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.sports_analysis.attendance_access import (
    SportsAnalysisAuthorizationError,
    get_current_sports_analysis_user,
    resolve_sports_analysis_scope,
)
from app.sports_analysis.attendance_query_service import (
    SportsAnalysisValidationError,
    attendance_catalogs,
    attendance_dashboard,
    attendance_runs,
)


sports_analysis_bp = Blueprint(
    "sports_analysis",
    __name__,
)


def _scope():
    user = get_current_sports_analysis_user()
    return (
        user,
        resolve_sports_analysis_scope(user),
    )


def _parse_date_arg(
    name: str,
) -> date | None:
    raw = str(
        request.args.get(name) or ""
    ).strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise SportsAnalysisValidationError(
            f"{name} debe tener formato "
            "YYYY-MM-DD."
        ) from exc


def _parse_int_arg(
    name: str,
) -> int | None:
    raw = request.args.get(name)
    if raw in (None, ""):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise SportsAnalysisValidationError(
            f"{name} inválido."
        ) from exc
    if value <= 0:
        raise SportsAnalysisValidationError(
            f"{name} inválido."
        )
    return value


@sports_analysis_bp.errorhandler(
    SportsAnalysisAuthorizationError
)
def _handle_authorization(exc):
    db.session.rollback()
    return jsonify(
        {
            "error": "Forbidden",
            "detail": str(exc),
        }
    ), 403


@sports_analysis_bp.errorhandler(
    SportsAnalysisValidationError
)
def _handle_validation(exc):
    db.session.rollback()
    return jsonify(
        {
            "error": "Bad Request",
            "detail": str(exc),
        }
    ), 400


@sports_analysis_bp.get("/context")
@jwt_required()
def sports_analysis_context():
    user, scope = _scope()
    return jsonify(
        {
            "allowed": True,
            "user": {
                "id": int(user.id),
                "username": user.username,
                "role": user.rol,
            },
            "scope": {
                "role": scope.role,
                "is_global": scope.is_global,
                "allowed_branch_ids": list(
                    scope.allowed_branch_ids
                ),
                "fixed_branch_id": (
                    scope.fixed_branch_id
                ),
            },
        }
    ), 200


@sports_analysis_bp.get(
    "/attendance/catalogs"
)
@jwt_required()
def get_attendance_catalogs():
    _, scope = _scope()
    return jsonify(
        attendance_catalogs(scope)
    ), 200


@sports_analysis_bp.get(
    "/attendance/dashboard"
)
@jwt_required()
def get_attendance_dashboard():
    _, scope = _scope()
    try:
        result = attendance_dashboard(
            scope,
            date_from=_parse_date_arg(
                "date_from"
            ),
            date_to=_parse_date_arg(
                "date_to"
            ),
            branch_id=_parse_int_arg(
                "branch_id"
            ),
            region_key=(
                str(
                    request.args.get(
                        "region_key"
                    )
                    or ""
                ).strip()
                or None
            ),
            attendance_type=(
                str(
                    request.args.get(
                        "attendance_type"
                    )
                    or ""
                ).strip()
                or None
            ),
        )
        return jsonify(result), 200
    except (
        SportsAnalysisAuthorizationError,
        SportsAnalysisValidationError,
    ):
        raise
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Error consultando "
            "Aforo y Asistencia."
        )
        return jsonify(
            {
                "error": (
                    "Internal Server Error"
                ),
                "detail": (
                    "No se pudo consultar "
                    "Aforo y Asistencia."
                ),
            }
        ), 500


@sports_analysis_bp.get(
    "/attendance/runs"
)
@jwt_required()
def get_attendance_runs():
    _, scope = _scope()
    limit = _parse_int_arg("limit") or 30
    return jsonify(
        attendance_runs(
            scope,
            limit=limit,
        )
    ), 200
