from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app, jsonify, request, send_file
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.extensions import db
from app.models.routine_control import RoutineControlMemberORM
from app.models.user_model import UserORM
from app.routine_control.domain.commands import (
    CreateNoRoutineDecisionCommand,
    RevokeNoRoutineDecisionCommand,
)
from app.routine_control.domain.exceptions import (
    RoutineControlDecisionConflict,
    RoutineControlDecisionNotFound,
    RoutineControlDecisionValidationError,
)
from app.routine_control.services.decision_service import (
    create_no_routine_decision,
    revoke_no_routine_decision,
)
from app.routine_control.queries import (
    RoutineControlAuthorizationError,
    RoutineControlOperationalRepository,
    RoutineControlOperationalService,
    RoutineControlValidationError,
    build_members_export,
)


routine_control_bp = Blueprint("routine_control", __name__)


DECISION_WRITE_ROLES = frozenset(
    {
        "ADMIN",
        "ADMINISTRADOR",
        "SUPER_ADMIN",
        "GERENTE",
        "GERENTE_REGIONAL",
    }
)


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


def _authorized_decision_user(
    member_id: int,
) -> UserORM:
    user = _current_user()
    service = _service()
    scope = service.resolve_scope(user)

    if scope.role not in DECISION_WRITE_ROLES:
        raise RoutineControlAuthorizationError(
            "Tu rol sólo permite consultar Control de Rutinas."
        )

    member = db.session.get(
        RoutineControlMemberORM,
        member_id,
    )

    if member is None:
        raise RoutineControlDecisionNotFound(
            "El socio solicitado no existe."
        )

    if member.sucursal_id not in set(
        scope.allowed_branch_ids
    ):
        raise RoutineControlAuthorizationError(
            "Socio fuera del alcance autorizado."
        )

    return user


def _json_object() -> dict:
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        raise RoutineControlDecisionValidationError(
            "El cuerpo debe ser un objeto JSON."
        )

    return payload


def _decision_result_dto(result) -> dict:
    return {
        "decision_id": result.decision_id,
        "member_id": result.member_id,
        "action": result.action,
        "is_active": result.is_active,
        "reason_code": result.reason_code,
        "notes": result.notes,
        "decided_at_utc": (
            result.decided_at_utc.isoformat()
        ),
        "revoked_at_utc": (
            result.revoked_at_utc.isoformat()
            if result.revoked_at_utc is not None
            else None
        ),
        "classification_status": (
            result.classification_status
        ),
        "current_status": result.current_status,
        "status_version": result.status_version,
    }


def _error_response(exc: Exception):
    if isinstance(exc, RoutineControlAuthorizationError):
        return jsonify({
            "error": "Forbidden",
            "detail": str(exc),
        }), 403

    if isinstance(exc, RoutineControlDecisionNotFound):
        return jsonify({
            "error": "Not Found",
            "detail": str(exc),
        }), 404

    if isinstance(exc, RoutineControlDecisionConflict):
        return jsonify({
            "error": "Conflict",
            "detail": str(exc),
        }), 409

    if isinstance(
        exc,
        (
            RoutineControlValidationError,
            RoutineControlDecisionValidationError,
        ),
    ):
        return jsonify({
            "error": "Bad Request",
            "detail": str(exc),
        }), 400
    current_app.logger.exception("Error en consulta operativa de Control de Rutinas")
    return jsonify({
        "error": "Internal Server Error",
        "detail": "No se pudo completar la consulta de Control de Rutinas.",
    }), 500


@routine_control_bp.get("/catalogs")
@jwt_required()
def routine_control_catalogs():
    try:
        return jsonify(
            _service().catalogs(
                _current_user(),
                request.args,
            )
        ), 200
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


@routine_control_bp.post(
    "/members/<int:member_id>/no-routine-decision"
)
@jwt_required()
def routine_control_create_no_routine_decision(
    member_id: int,
):
    try:
        user = _authorized_decision_user(member_id)
        payload = _json_object()

        result = create_no_routine_decision(
            CreateNoRoutineDecisionCommand(
                member_id=member_id,
                reason_code=payload.get("reason_code"),
                notes=payload.get("notes"),
                actor_user_id=int(user.id),
                confirmed=payload.get("confirmed"),
            )
        )

        return jsonify(
            _decision_result_dto(result)
        ), 201
    except Exception as exc:
        return _error_response(exc)


@routine_control_bp.post(
    "/members/<int:member_id>/no-routine-decision/"
    "<int:decision_id>/revoke"
)
@jwt_required()
def routine_control_revoke_no_routine_decision(
    member_id: int,
    decision_id: int,
):
    try:
        user = _authorized_decision_user(member_id)
        payload = _json_object()

        result = revoke_no_routine_decision(
            RevokeNoRoutineDecisionCommand(
                member_id=member_id,
                decision_id=decision_id,
                actor_user_id=int(user.id),
                revocation_reason=payload.get(
                    "revocation_reason"
                ),
            )
        )

        return jsonify(
            _decision_result_dto(result)
        ), 200
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
