from __future__ import annotations

from datetime import date

from flask import (
    Blueprint,
    current_app,
    jsonify,
    request,
    send_file,
)
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.sports_analysis.attendance_access import (
    SportsAnalysisAuthorizationError,
    get_current_sports_analysis_user,
    resolve_sports_analysis_scope,
)
from app.sports_analysis.attendance_detail_service import (
    DETAIL_EXPORT_MIMETYPE,
    build_attendance_detail,
    build_attendance_detail_export,
)
from app.sports_analysis.attendance_export_service import (
    ATTENDANCE_EXPORT_MIMETYPE,
)
from app.sports_analysis.attendance_base_health_service import (
    attendance_base_health,
    attendance_base_health_members,
    attendance_base_health_members_export,
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


SERVER_TIMING_ORDER = (
    "scope",
    "socios_activos",
    "visitas_periodo",
    "visitas_consulta",
    "visitas_identidad",
    "visitas_fallback",
    "fallback_exact",
    "fallback_snapshots",
    "fallback_pin",
    "fallback_branch",
    "historico",
    "historico_identidad",
    "historico_visitas",
    "hist_q1",
    "hist_q2",
    "hist_q3",
    "hist_q4",
    "hist_q5",
    "hist_q6",
    "hist_q7",
    "hist_q8",
    "cohorte",
    "serializacion",
    "metricas",
    "total",
)


def _server_timing_header(
    timings: dict[str, float],
) -> str:
    return ", ".join(
        (
            f"{name};dur="
            f"{timings[name]:.2f}"
        )
        for name in SERVER_TIMING_ORDER
        if name in timings
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


def _parse_nonnegative_int_arg(
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
    if value < 0:
        raise SportsAnalysisValidationError(
            f"{name} inválido."
        )
    return value


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
    "/attendance/base-health"
)
@jwt_required()
def get_attendance_base_health():
    _, scope = _scope()
    date_from = _parse_date_arg("date_from")
    date_to = _parse_date_arg("date_to")
    if date_from is None or date_to is None:
        raise SportsAnalysisValidationError(
            "date_from y date_to son obligatorios."
        )

    try:
        timings: dict[str, float] = {}
        result = attendance_base_health(
            scope,
            date_from=date_from,
            date_to=date_to,
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
            timings=timings,
        )
        response = jsonify(result)
        response.headers["Server-Timing"] = (
            _server_timing_header(timings)
        )
        return response, 200
    except (
        SportsAnalysisAuthorizationError,
        SportsAnalysisValidationError,
    ):
        raise
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Error consultando Salud de la base."
        )
        return jsonify(
            {
                "error": (
                    "Internal Server Error"
                ),
                "detail": (
                    "No se pudo consultar "
                    "Salud de la base."
                ),
            }
        ), 500


@sports_analysis_bp.get(
    "/attendance/base-health/members"
)
@jwt_required()
def get_attendance_base_health_members():
    _, scope = _scope()
    date_from = _parse_date_arg("date_from")
    date_to = _parse_date_arg("date_to")
    if date_from is None or date_to is None:
        raise SportsAnalysisValidationError(
            "date_from y date_to son obligatorios."
        )

    try:
        timings: dict[str, float] = {}
        result = attendance_base_health_members(
            scope,
            date_from=date_from,
            date_to=date_to,
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
            status=str(
                request.args.get("status")
                or ""
            ),
            tariff=(
                str(
                    request.args.get("tariff")
                    or ""
                ).strip()
                or None
            ),
            page=request.args.get("page"),
            page_size=request.args.get(
                "page_size"
            ),
            timings=timings,
        )
        response = jsonify(result)
        response.headers["Server-Timing"] = (
            _server_timing_header(timings)
        )
        return response, 200
    except (
        SportsAnalysisAuthorizationError,
        SportsAnalysisValidationError,
    ):
        raise
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Error consultando detalle "
            "de Salud de la base."
        )
        return jsonify(
            {
                "error": (
                    "Internal Server Error"
                ),
                "detail": (
                    "No se pudo consultar el "
                    "detalle de Salud de la base."
                ),
            }
        ), 500


@sports_analysis_bp.get(
    "/attendance/base-health/members/export"
)
@jwt_required()
def export_attendance_base_health_members():
    _, scope = _scope()
    date_from = _parse_date_arg("date_from")
    date_to = _parse_date_arg("date_to")
    if date_from is None or date_to is None:
        raise SportsAnalysisValidationError(
            "date_from y date_to son obligatorios."
        )

    try:
        output, filename = (
            attendance_base_health_members_export(
                scope,
                date_from=date_from,
                date_to=date_to,
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
                status=str(
                    request.args.get("status")
                    or ""
                ),
                tariff=(
                    str(
                        request.args.get("tariff")
                        or ""
                    ).strip()
                    or None
                ),
            )
        )
        return send_file(
            output,
            mimetype=ATTENDANCE_EXPORT_MIMETYPE,
            as_attachment=True,
            download_name=filename,
        )
    except (
        SportsAnalysisAuthorizationError,
        SportsAnalysisValidationError,
    ):
        raise
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Error exportando detalle "
            "de Salud de la base."
        )
        return jsonify(
            {
                "error": (
                    "Internal Server Error"
                ),
                "detail": (
                    "No se pudo exportar el "
                    "detalle de Salud de la base."
                ),
            }
        ), 500


@sports_analysis_bp.get(
    "/attendance/detail"
)
@jwt_required()
def get_attendance_detail():
    _, scope = _scope()
    date_from = _parse_date_arg("date_from")
    date_to = _parse_date_arg("date_to")
    if date_from is None or date_to is None:
        raise SportsAnalysisValidationError(
            "date_from y date_to son obligatorios."
        )

    return jsonify(
        build_attendance_detail(
            scope,
            metric=str(
                request.args.get("metric") or ""
            ),
            date_from=date_from,
            date_to=date_to,
            branch_id=_parse_int_arg("branch_id"),
            region_key=(
                str(
                    request.args.get("region_key")
                    or ""
                ).strip()
                or None
            ),
            attendance_type=(
                str(
                    request.args.get("attendance_type")
                    or ""
                ).strip()
                or None
            ),
            page=request.args.get("page"),
            page_size=request.args.get("page_size"),
            sort_by=(
                str(
                    request.args.get("sort_by")
                    or ""
                ).strip()
                or None
            ),
            sort_dir=(
                str(
                    request.args.get("sort_dir")
                    or ""
                ).strip()
                or None
            ),
            minute=_parse_nonnegative_int_arg(
                "minute"
            ),
            hour=_parse_nonnegative_int_arg(
                "hour"
            ),
            age_bucket=(
                str(
                    request.args.get("age_bucket")
                    or ""
                ).strip()
                or None
            ),
        )
    ), 200


@sports_analysis_bp.get(
    "/attendance/detail/export"
)
@jwt_required()
def export_attendance_detail():
    _, scope = _scope()
    date_from = _parse_date_arg("date_from")
    date_to = _parse_date_arg("date_to")
    if date_from is None or date_to is None:
        raise SportsAnalysisValidationError(
            "date_from y date_to son obligatorios."
        )

    output, filename = build_attendance_detail_export(
        scope,
        metric=str(
            request.args.get("metric") or ""
        ),
        date_from=date_from,
        date_to=date_to,
        branch_id=_parse_int_arg("branch_id"),
        region_key=(
            str(
                request.args.get("region_key")
                or ""
            ).strip()
            or None
        ),
        attendance_type=(
            str(
                request.args.get("attendance_type")
                or ""
            ).strip()
            or None
        ),
        sort_by=(
            str(
                request.args.get("sort_by")
                or ""
            ).strip()
            or None
        ),
        sort_dir=(
            str(
                request.args.get("sort_dir")
                or ""
            ).strip()
            or None
        ),
        minute=_parse_nonnegative_int_arg(
            "minute"
        ),
        hour=_parse_nonnegative_int_arg(
            "hour"
        ),
        age_bucket=(
            str(
                request.args.get("age_bucket")
                or ""
            ).strip()
            or None
        ),
    )
    return send_file(
        output,
        mimetype=DETAIL_EXPORT_MIMETYPE,
        as_attachment=True,
        download_name=filename,
    )


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
