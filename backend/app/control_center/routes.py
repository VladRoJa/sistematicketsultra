from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.control_center.access import (
    ControlAuthorizationError,
    ControlValidationError,
    resolve_control_access,
    resolve_effective_scope,
)
from app.control_center.retention import build_retention_summary
from app.models.user_model import UserORM


control_center_bp = Blueprint("control_center", __name__)
BUSINESS_TZ = ZoneInfo("America/Tijuana")


def _get_current_user() -> UserORM:
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError) as exc:
        raise ControlAuthorizationError(
            "No autorizado para consultar el Centro de Control."
        ) from exc

    user = UserORM.get_by_id(user_id)
    if user is None:
        raise ControlAuthorizationError("Usuario no encontrado.")
    return user


def _parse_cutoff_date():
    raw_value = str(request.args.get("cutoff_date") or "").strip()
    if not raw_value:
        return datetime.now(BUSINESS_TZ).date()

    try:
        return datetime.strptime(raw_value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ControlValidationError(
            "cutoff_date inválido. Usa YYYY-MM-DD."
        ) from exc


def _resolve_request_context():
    cutoff_date = _parse_cutoff_date()
    user = _get_current_user()
    access = resolve_control_access(
        user,
        as_of_date=cutoff_date,
    )
    effective_scope = resolve_effective_scope(
        access,
        as_of_date=cutoff_date,
        requested_scope_type=request.args.get("scope_type"),
        region_key=request.args.get("region_key"),
        branch_id=request.args.get("branch_id"),
    )
    return cutoff_date, access, effective_scope


@control_center_bp.get("/context")
@jwt_required()
def get_control_context():
    try:
        cutoff_date, access, effective_scope = _resolve_request_context()

        return jsonify(
            {
                "status": "ok",
                "contract_version": "control.v1",
                "cutoff_date": cutoff_date.isoformat(),
                "access": access.to_public_dict(),
                "effective_scope": effective_scope.to_public_dict(),
            }
        ), 200
    except ControlAuthorizationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    except ControlValidationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400


@control_center_bp.get("/retention")
@jwt_required()
def get_control_retention():
    try:
        cutoff_date, _access, effective_scope = _resolve_request_context()
        generation_mode = str(
            request.args.get("generation_mode") or "manual_preview"
        ).strip()
        if generation_mode not in {"manual_preview", "official_closed_day"}:
            raise ControlValidationError("generation_mode inválido.")

        result = build_retention_summary(
            cutoff_date=cutoff_date,
            effective_scope=effective_scope,
            generation_mode=generation_mode,
        )
        result["contract_version"] = "control.retention.v1"
        result["effective_scope"] = effective_scope.to_public_dict()
        return jsonify(result), 200
    except ControlAuthorizationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    except ControlValidationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception as exc:
        return jsonify(
            {
                "status": "error",
                "message": "Falló la consulta de Retención para Control.",
                "detail": str(exc),
            }
        ), 500
