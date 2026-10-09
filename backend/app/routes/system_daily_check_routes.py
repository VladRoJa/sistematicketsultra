from __future__ import annotations

import json

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.extensions import db
from app.models.user_model import UserORM
from app.services.system_daily_check_attachment_service import (
    MAX_SYSTEM_DAILY_CHECK_ATTACHMENT_BYTES,
    cleanup_system_daily_check_attachments,
    create_system_daily_check_issue_attachment,
)
from app.services.system_daily_check_service import (
    SystemDailyCheckAuthorizationError,
    SystemDailyCheckConflictError,
    SystemDailyCheckNotFoundError,
    SystemDailyCheckValidationError,
    get_today_status,
    list_system_daily_check_branches,
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

    if isinstance(error, SystemDailyCheckNotFoundError):
        return jsonify({
            "error": "NotFound",
            "code": "SYSTEM_DAILY_CHECK_NOT_FOUND",
            "detail": str(error),
        }), 404

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


def _validate_submit_payload_shape(payload: object) -> dict:
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


def _parse_submit_request() -> tuple[dict, dict[str, list]]:
    if request.is_json:
        return _validate_submit_payload_shape(
            request.get_json(silent=True)
        ), {}

    if not (
        request.mimetype
        and request.mimetype.startswith("multipart/form-data")
    ):
        raise SystemDailyCheckValidationError(
            "Content-Type inválido para enviar el checklist."
        )

    raw_payload = request.form.get("payload")
    if not raw_payload:
        raise SystemDailyCheckValidationError(
            "payload es obligatorio en multipart/form-data."
        )

    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        raise SystemDailyCheckValidationError(
            "payload contiene JSON inválido."
        ) from exc

    evidence_by_question: dict[str, list] = {}
    for field_name, uploaded in request.files.items(multi=True):
        prefix = "evidence__"
        if not field_name.startswith(prefix):
            raise SystemDailyCheckValidationError(
                f"Campo de archivo no reconocido: {field_name}."
            )

        question_key = field_name[len(prefix):].strip().upper()
        if not question_key:
            raise SystemDailyCheckValidationError(
                "La evidencia debe indicar question_key."
            )
        evidence_by_question.setdefault(question_key, []).append(
            uploaded
        )

    return (
        _validate_submit_payload_shape(payload),
        evidence_by_question,
    )


def _attach_submit_evidence(
    *,
    check,
    evidence_by_question: dict[str, list],
    actor,
    written_storage_keys: list[str],
) -> None:
    if not evidence_by_question:
        return

    issues_by_question = {
        answer.question_key: answer.issue
        for answer in check.answers
        if answer.issue is not None
    }

    for question_key, uploaded_files in evidence_by_question.items():
        issue = issues_by_question.get(question_key)
        if issue is None:
            raise SystemDailyCheckValidationError(
                "La evidencia solo puede adjuntarse a una respuesta NO: "
                f"{question_key}."
            )

        for uploaded in uploaded_files:
            content = uploaded.read(
                MAX_SYSTEM_DAILY_CHECK_ATTACHMENT_BYTES + 1
            )
            if len(content) > MAX_SYSTEM_DAILY_CHECK_ATTACHMENT_BYTES:
                raise SystemDailyCheckValidationError(
                    "El archivo excede el límite máximo de 15 MB."
                )

            attachment, storage_key = (
                create_system_daily_check_issue_attachment(
                    issue_id=issue.id,
                    content=content,
                    original_filename=uploaded.filename or "",
                    declared_mime_type=uploaded.mimetype,
                    actor=actor,
                    session=db.session,
                )
            )
            written_storage_keys.append(storage_key)
            issue.attachments.append(attachment)


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


@system_daily_check_bp.route("/branches", methods=["GET"])
@jwt_required()
def branches():
    try:
        actor = _current_user()
        return jsonify(
            list_system_daily_check_branches(actor)
        ), 200
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
    written_storage_keys: list[str] = []
    try:
        actor = _current_user()
        payload, evidence_by_question = _parse_submit_request()
        check = submit_today(
            actor,
            payload,
            requested_branch_id=_requested_branch_id(),
        )
        _attach_submit_evidence(
            check=check,
            evidence_by_question=evidence_by_question,
            actor=actor,
            written_storage_keys=written_storage_keys,
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
        SystemDailyCheckNotFoundError,
    ) as exc:
        db.session.rollback()
        cleanup_system_daily_check_attachments(
            written_storage_keys
        )
        return _error_response(exc)
    except Exception:
        db.session.rollback()
        cleanup_system_daily_check_attachments(
            written_storage_keys
        )
        current_app.logger.exception(
            "Unexpected error submitting system daily check."
        )
        return jsonify({
            "error": "InternalServerError",
            "code": "SYSTEM_DAILY_CHECK_INTERNAL_ERROR",
        }), 500
