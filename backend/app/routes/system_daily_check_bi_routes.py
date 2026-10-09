from __future__ import annotations

from datetime import date

from flask import Blueprint, current_app, jsonify, request, send_file
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.extensions import db
from app.models.user_model import UserORM
from app.services.system_daily_check_bi_service import (
    build_system_daily_check_bi_matrix,
    build_system_daily_check_bi_summary,
    build_system_daily_check_bi_trends,
    configure_system_daily_check_rollout_today,
    get_system_daily_check_bi_attachment,
    get_system_daily_check_bi_detail,
    list_system_daily_check_bi_history,
    list_system_daily_check_bi_issues,
    list_system_daily_check_bi_pending,
    resolve_system_daily_check_branch_universe,
)
from app.services.system_daily_check_service import (
    SystemDailyCheckAuthorizationError,
    SystemDailyCheckNotFoundError,
    SystemDailyCheckValidationError,
    list_system_daily_check_questions,
    resolve_business_date,
)
from app.utils.system_daily_check_access import (
    has_system_daily_check_mvp_access,
)


system_daily_check_bi_bp = Blueprint(
    "system_daily_check_bi",
    __name__,
)


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


def _require_bi_access(actor) -> None:
    if not has_system_daily_check_mvp_access(actor):
        raise SystemDailyCheckAuthorizationError(
            "El usuario no está habilitado para BI del checklist diario."
        )




def _parse_date_arg(name: str, *, default=None):
    raw = str(request.args.get(name) or "").strip()
    if not raw:
        return default
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise SystemDailyCheckValidationError(
            f"{name} debe tener formato YYYY-MM-DD."
        ) from exc


def _parse_branch_id_arg():
    raw = request.args.get("branch_id")
    if raw in (None, ""):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise SystemDailyCheckValidationError(
            "branch_id debe ser entero."
        ) from exc
    if value <= 0:
        raise SystemDailyCheckValidationError(
            "branch_id inválido."
        )
    return value


def _parse_optional_bool_arg(name: str):
    raw = str(request.args.get(name) or "").strip().lower()
    if not raw:
        return None
    if raw in {"true", "1", "yes"}:
        return True
    if raw in {"false", "0", "no"}:
        return False
    raise SystemDailyCheckValidationError(
        f"{name} debe ser booleano."
    )


def _error_response(error: Exception):
    if isinstance(error, SystemDailyCheckAuthorizationError):
        return jsonify({
            "error": "Forbidden",
            "code": "SYSTEM_DAILY_CHECK_BI_NOT_ELIGIBLE",
            "allowed": False,
            "detail": str(error),
        }), 403

    if isinstance(error, SystemDailyCheckValidationError):
        return jsonify({
            "error": "ValidationError",
            "code": "SYSTEM_DAILY_CHECK_BI_VALIDATION_ERROR",
            "detail": str(error),
        }), 400

    if isinstance(error, SystemDailyCheckNotFoundError):
        return jsonify({
            "error": "NotFound",
            "code": "SYSTEM_DAILY_CHECK_BI_NOT_FOUND",
            "detail": str(error),
        }), 404

    raise error


@system_daily_check_bi_bp.get("/context")
@jwt_required()
def bi_context():
    try:
        actor = _current_user()
        _require_bi_access(actor)
        business_date = resolve_business_date()
        return jsonify({
            "allowed": True,
            "user": {
                "id": int(actor.id),
                "username": actor.username,
                "role": actor.rol,
            },
            "business_date": business_date.isoformat(),
            "questions": list_system_daily_check_questions(),
            "universe": resolve_system_daily_check_branch_universe(
                as_of_date=business_date,
            ),
        }), 200
    except (
        SystemDailyCheckAuthorizationError,
        SystemDailyCheckValidationError,
    ) as exc:
        return _error_response(exc)




@system_daily_check_bi_bp.get("/summary")
@jwt_required()
def bi_summary():
    try:
        actor = _current_user()
        _require_bi_access(actor)
        business_date = resolve_business_date()
        date_from = _parse_date_arg(
            "date_from",
            default=business_date,
        )
        date_to = _parse_date_arg(
            "date_to",
            default=date_from,
        )
        result = build_system_daily_check_bi_summary(
            actor,
            date_from=date_from,
            date_to=date_to,
            branch_id=_parse_branch_id_arg(),
        )
        return jsonify(result), 200
    except (
        SystemDailyCheckAuthorizationError,
        SystemDailyCheckValidationError,
    ) as exc:
        return _error_response(exc)




@system_daily_check_bi_bp.get("/matrix")
@jwt_required()
def bi_matrix():
    try:
        actor = _current_user()
        _require_bi_access(actor)
        business_date = _parse_date_arg(
            "date",
            default=resolve_business_date(),
        )
        result = build_system_daily_check_bi_matrix(
            actor,
            business_date=business_date,
            branch_id=_parse_branch_id_arg(),
        )
        return jsonify(result), 200
    except (
        SystemDailyCheckAuthorizationError,
        SystemDailyCheckValidationError,
    ) as exc:
        return _error_response(exc)






@system_daily_check_bi_bp.get("/trends")
@jwt_required()
def bi_trends():
    try:
        actor = _current_user()
        _require_bi_access(actor)
        business_date = resolve_business_date()
        date_from = _parse_date_arg(
            "date_from",
            default=business_date,
        )
        date_to = _parse_date_arg(
            "date_to",
            default=date_from,
        )
        result = build_system_daily_check_bi_trends(
            actor,
            date_from=date_from,
            date_to=date_to,
            granularity=request.args.get(
                "granularity",
                "DAY",
            ),
            branch_id=_parse_branch_id_arg(),
        )
        return jsonify(result), 200
    except (
        SystemDailyCheckAuthorizationError,
        SystemDailyCheckValidationError,
    ) as exc:
        return _error_response(exc)




@system_daily_check_bi_bp.get("/pending")
@jwt_required()
def bi_pending():
    try:
        actor = _current_user()
        _require_bi_access(actor)
        business_date = resolve_business_date()
        date_from = _parse_date_arg(
            "date_from",
            default=business_date,
        )
        date_to = _parse_date_arg(
            "date_to",
            default=date_from,
        )
        result = list_system_daily_check_bi_pending(
            actor,
            date_from=date_from,
            date_to=date_to,
            branch_id=_parse_branch_id_arg(),
            page=request.args.get("page", 1),
            page_size=request.args.get("page_size", 50),
        )
        return jsonify(result), 200
    except (
        SystemDailyCheckAuthorizationError,
        SystemDailyCheckValidationError,
    ) as exc:
        return _error_response(exc)


@system_daily_check_bi_bp.get("/history")
@jwt_required()
def bi_history():
    try:
        actor = _current_user()
        _require_bi_access(actor)
        business_date = resolve_business_date()
        date_from = _parse_date_arg(
            "date_from",
            default=business_date,
        )
        date_to = _parse_date_arg(
            "date_to",
            default=date_from,
        )
        result = list_system_daily_check_bi_history(
            actor,
            date_from=date_from,
            date_to=date_to,
            branch_id=_parse_branch_id_arg(),
            general_status=request.args.get("general_status"),
            question_key=request.args.get("question_key"),
            answer=request.args.get("answer"),
            page=request.args.get("page", 1),
            page_size=request.args.get("page_size", 50),
        )
        return jsonify(result), 200
    except (
        SystemDailyCheckAuthorizationError,
        SystemDailyCheckValidationError,
    ) as exc:
        return _error_response(exc)




@system_daily_check_bi_bp.get("/issues")
@jwt_required()
def bi_issues():
    try:
        actor = _current_user()
        _require_bi_access(actor)
        business_date = resolve_business_date()
        date_from = _parse_date_arg(
            "date_from",
            default=business_date,
        )
        date_to = _parse_date_arg(
            "date_to",
            default=date_from,
        )
        result = list_system_daily_check_bi_issues(
            actor,
            date_from=date_from,
            date_to=date_to,
            branch_id=_parse_branch_id_arg(),
            question_key=request.args.get("question_key"),
            reported_to_support=_parse_optional_bool_arg(
                "reported_to_support"
            ),
            page=request.args.get("page", 1),
            page_size=request.args.get("page_size", 100),
        )
        return jsonify(result), 200
    except (
        SystemDailyCheckAuthorizationError,
        SystemDailyCheckValidationError,
    ) as exc:
        return _error_response(exc)


@system_daily_check_bi_bp.get("/checks/<int:check_id>")
@jwt_required()
def bi_check_detail(check_id: int):
    try:
        actor = _current_user()
        _require_bi_access(actor)
        return jsonify(
            get_system_daily_check_bi_detail(
                actor,
                check_id=check_id,
            )
        ), 200
    except (
        SystemDailyCheckAuthorizationError,
        SystemDailyCheckValidationError,
        SystemDailyCheckNotFoundError,
    ) as exc:
        return _error_response(exc)




@system_daily_check_bi_bp.get("/attachments/<int:attachment_id>")
@jwt_required()
def bi_attachment(attachment_id: int):
    try:
        actor = _current_user()
        _require_bi_access(actor)
        resolved = get_system_daily_check_bi_attachment(
            actor,
            attachment_id=attachment_id,
        )
        return send_file(
            resolved["path"],
            mimetype=resolved["mime_type"],
            as_attachment=False,
            download_name=resolved["original_filename"],
            conditional=True,
        )
    except (
        SystemDailyCheckAuthorizationError,
        SystemDailyCheckValidationError,
        SystemDailyCheckNotFoundError,
    ) as exc:
        return _error_response(exc)


@system_daily_check_bi_bp.put("/rollout")
@jwt_required()
def bi_rollout():
    try:
        actor = _current_user()
        _require_bi_access(actor)
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise SystemDailyCheckValidationError(
                "El body debe ser un objeto JSON."
            )

        result = configure_system_daily_check_rollout_today(
            actor,
            branch_ids=payload.get("branch_ids"),
        )
        db.session.commit()
        return jsonify({
            "allowed": True,
            "universe": result,
        }), 200
    except (
        SystemDailyCheckAuthorizationError,
        SystemDailyCheckValidationError,
    ) as exc:
        db.session.rollback()
        return _error_response(exc)
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Unexpected error configuring system daily check rollout."
        )
        return jsonify({
            "error": "InternalServerError",
            "code": "SYSTEM_DAILY_CHECK_BI_INTERNAL_ERROR",
        }), 500
