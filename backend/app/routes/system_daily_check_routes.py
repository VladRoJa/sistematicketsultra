from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.extensions import db
from app.models.user_model import UserORM
from app.services.system_daily_check_service import (
    SystemDailyCheckAuthorizationError,
    SystemDailyCheckConflictError,
    SystemDailyCheckValidationError,
    get_today_status,
    list_system_daily_check_questions,
    postpone_today,
    submit_today,
)
from app.utils.system_daily_check_access import has_system_daily_check_mvp_access


system_daily_check_bp = Blueprint(
    "system_daily_check",
    __name__,
)

SERVER_CONTROLLED_SUBMIT_FIELDS = frozenset({
    "sucursal_id",
    "branch_id",
    "business_date",
    "performed_by_user_id",
    "user_id",
    "created_at",
    "submitted_at",
})


def _error_response(error: Exception):
    if isinstance(error, SystemDailyCheckAuthorizationError):
        return jsonify({
            "error": "Forbidden",
            "code": "SYSTEM_DAILY_CHECK_NOT_ELIGIBLE",
            "eligible": False,
            "detail": str(error),
        }), 403

    if isinstance(error, SystemDailyCheckValidationError):
        return jsonify({
            "error": "ValidationError",
            "code": "SYSTEM_DAILY_CHECK_VALIDATION_ERROR",
            "detail": str(error),
        }), 400

    if isinstance(error, SystemDailyCheckConflictError):
        return jsonify({
            "error": "Conflict",
            "code": "SYSTEM_DAILY_CHECK_CONFLICT",
            "detail": str(error),
        }), 409

    raise error


def _current_user():
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError) as exc:
        raise SystemDailyCheckAuthorizationError(
            "Identidad de usuario inválida."
        ) from exc

    user = UserORM.get_by_id(user_id)
    if user is None:
        raise SystemDailyCheckAuthorizationError(
            "Usuario no encontrado."
        )
    return user


def _requested_branch_id():
    return request.args.get("sucursal_id")


def _require_submit_payload() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise SystemDailyCheckValidationError(
            "El body debe ser un objeto JSON."
        )

    forbidden = sorted(
        field
        for field in SERVER_CONTROLLED_SUBMIT_FIELDS
        if field in payload
    )
    if forbidden:
        raise SystemDailyCheckValidationError(
            "El body contiene campos controlados por el servidor: "
            + ", ".join(forbidden)
            + "."
        )
    return payload


@system_daily_check_bp.route("/questions", methods=["GET"])
@jwt_required()
def questions():
    try:
        actor = _current_user()
        if not has_system_daily_check_mvp_access(actor):
            raise SystemDailyCheckAuthorizationError(
                "El usuario no está habilitado para el piloto del checklist diario."
            )
        return jsonify({
            "eligible": True,
            "questions": list_system_daily_check_questions(),
        }), 200
    except (
        SystemDailyCheckAuthorizationError,
        SystemDailyCheckValidationError,
        SystemDailyCheckConflictError,
    ) as exc:
        return _error_response(exc)


@system_daily_check_bp.route("/today/status", methods=["GET"])
@jwt_required()
def today_status():
    try:
        actor = _current_user()
        payload = get_today_status(
            actor,
            requested_branch_id=_requested_branch_id(),
        )
        return jsonify(payload), 200
    except (
        SystemDailyCheckAuthorizationError,
        SystemDailyCheckValidationError,
        SystemDailyCheckConflictError,
    ) as exc:
        return _error_response(exc)


@system_daily_check_bp.route("/today/postpone", methods=["POST"])
@jwt_required()
def today_postpone():
    try:
        actor = _current_user()
        payload = postpone_today(
            actor,
            requested_branch_id=_requested_branch_id(),
        )
        db.session.commit()
        return jsonify(payload), 200
    except (
        SystemDailyCheckAuthorizationError,
        SystemDailyCheckValidationError,
        SystemDailyCheckConflictError,
    ) as exc:
        db.session.rollback()
        return _error_response(exc)
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Unexpected error postponing system daily check."
        )
        return jsonify({
            "error": "InternalServerError",
            "code": "SYSTEM_DAILY_CHECK_INTERNAL_ERROR",
        }), 500


@system_daily_check_bp.route("/today/submit", methods=["POST"])
@jwt_required()
def today_submit():
    try:
        actor = _current_user()
        payload = _require_submit_payload()
        check = submit_today(
            actor,
            payload,
            requested_branch_id=_requested_branch_id(),
        )
        db.session.commit()
        return jsonify({
            "id": check.id,
            "sucursal_id": check.sucursal_id,
            "business_date": check.business_date.isoformat(),
            "performed_by_user_id": check.performed_by_user_id,
            "general_status": check.general_status,
            "submitted_at": (
                check.submitted_at.isoformat()
                if check.submitted_at is not None
                else None
            ),
        }), 201
    except (
        SystemDailyCheckAuthorizationError,
        SystemDailyCheckValidationError,
        SystemDailyCheckConflictError,
    ) as exc:
        db.session.rollback()
        return _error_response(exc)
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Unexpected error submitting system daily check."
        )
        return jsonify({
            "error": "InternalServerError",
            "code": "SYSTEM_DAILY_CHECK_INTERNAL_ERROR",
        }), 500
