from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.extensions import db
from app.models.rpa import GascaSmsRequestORM
from app.models.user_model import UserORM
from app.rpa.services.gasca_sms_request_service import (
    GascaSmsRequestMotivo,
    create_and_process_gasca_sms_request,
)


rpa_gasca_sms_bp = Blueprint("rpa_gasca_sms", __name__)

_RPA_GASCA_SMS_GLOBAL_ROLES = {
    "ADMIN",
    "ADMINISTRADOR",
    "SUPER_ADMIN",
    "SISTEMAS",
}

_RPA_GASCA_SMS_ALLOWED_ROLES = _RPA_GASCA_SMS_GLOBAL_ROLES | {
    "GERENTE",
    "GERENTE_REGIONAL",
}


def _role_norm(user: UserORM | None) -> str:
    return str(getattr(user, "rol", "") or "").strip().upper()


def _is_global_user(user: UserORM | None) -> bool:
    return _role_norm(user) in _RPA_GASCA_SMS_GLOBAL_ROLES


def _get_current_user() -> UserORM | None:
    raw_user_id = get_jwt_identity()

    try:
        user_id = int(raw_user_id)
    except (TypeError, ValueError):
        return None

    return UserORM.get_by_id(user_id)


def _normalizar_sucursales_ids(raw_value) -> list[int]:
    if raw_value is None:
        return []

    if not isinstance(raw_value, (list, tuple, set)):
        return []

    normalized: list[int] = []
    for item in raw_value:
        try:
            normalized.append(int(item))
        except (TypeError, ValueError):
            continue

    return sorted(set(normalized))


def _allowed_sucursales_for_user(user: UserORM | None) -> list[int]:
    if not user:
        return []

    allowed = _normalizar_sucursales_ids(getattr(user, "sucursales_ids", []))

    primary_sucursal_id = getattr(user, "sucursal_id", None)
    try:
        primary_sucursal_id = int(primary_sucursal_id) if primary_sucursal_id is not None else None
    except (TypeError, ValueError):
        primary_sucursal_id = None

    if primary_sucursal_id is not None:
        allowed.append(primary_sucursal_id)

    return sorted(set(allowed))


def _parse_optional_int(value, field_name: str):
    if value in (None, ""):
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} inválido.")


def _require_module_access(user: UserORM | None):
    if not user:
        return jsonify({"error": "Unauthorized", "detail": "Usuario no encontrado."}), 401

    role = _role_norm(user)
    if role not in _RPA_GASCA_SMS_ALLOWED_ROLES:
        return jsonify({"error": "Forbidden", "detail": "No tienes acceso a este módulo."}), 403

    return None


def _require_sucursal_access(user: UserORM | None, sucursal_id: int | None):
    forbidden = _require_module_access(user)
    if forbidden:
        return forbidden

    if _is_global_user(user):
        return None

    if sucursal_id is None:
        return jsonify({
            "error": "Bad Request",
            "detail": "sucursal_id es obligatorio para usuarios con alcance por sucursal.",
        }), 400

    allowed_sucursales = _allowed_sucursales_for_user(user)
    if sucursal_id not in allowed_sucursales:
        return jsonify({"error": "Forbidden", "detail": "No tienes acceso a esta sucursal."}), 403

    return None


def _request_visible_for_user(user: UserORM | None, item: GascaSmsRequestORM) -> bool:
    if not user:
        return False

    if _is_global_user(user):
        return True

    if item.requested_by_user_id == user.id:
        return True

    if item.sucursal_id is None:
        return False

    return item.sucursal_id in _allowed_sucursales_for_user(user)


@rpa_gasca_sms_bp.route("/catalogs", methods=["GET"])
@jwt_required()
def gasca_sms_catalogs():
    user = _get_current_user()
    forbidden = _require_module_access(user)
    if forbidden:
        return forbidden

    return jsonify({
        "motivos": list(GascaSmsRequestMotivo.ALL),
        "global_access": _is_global_user(user),
        "allowed_sucursales_ids": None if _is_global_user(user) else _allowed_sucursales_for_user(user),
    }), 200


@rpa_gasca_sms_bp.route("/requests", methods=["POST"])
@jwt_required()
def create_gasca_sms_request_route():
    user = _get_current_user()
    forbidden = _require_module_access(user)
    if forbidden:
        return forbidden

    data = request.get_json(silent=True) or {}

    try:
        pin_raw = str(data.get("pin") or data.get("pin_raw") or "").strip()
        phone_raw = str(data.get("telefono") or data.get("phone") or data.get("phone_raw") or "").strip()
        motivo = str(data.get("motivo") or "").strip()
        motivo_detalle = str(data.get("motivo_detalle") or "").strip() or None

        requested_sucursal_id = _parse_optional_int(data.get("sucursal_id"), "sucursal_id")
        if requested_sucursal_id is None:
            requested_sucursal_id = getattr(user, "sucursal_id", None)
            requested_sucursal_id = int(requested_sucursal_id) if requested_sucursal_id is not None else None

        forbidden = _require_sucursal_access(user, requested_sucursal_id)
        if forbidden:
            return forbidden

        item = create_and_process_gasca_sms_request(
            pin_raw=pin_raw,
            phone_raw=phone_raw,
            motivo=motivo,
            motivo_detalle=motivo_detalle,
            requested_by_user_id=user.id,
            sucursal_id=requested_sucursal_id,
        )

        return jsonify({
            "request": item.to_public_dict(),
            "message": item.user_message,
        }), 201

    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": "Bad Request", "detail": str(exc)}), 400

    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("Error creando solicitud Gasca SMS")
        return jsonify({
            "error": "Internal Server Error",
            "detail": "No se pudo procesar la solicitud Gasca SMS.",
        }), 500


@rpa_gasca_sms_bp.route("/requests", methods=["GET"])
@jwt_required()
def list_gasca_sms_requests_route():
    user = _get_current_user()
    forbidden = _require_module_access(user)
    if forbidden:
        return forbidden

    try:
        limit = _parse_optional_int(request.args.get("limit"), "limit") or 50
        limit = max(1, min(limit, 100))

        status = (request.args.get("status") or "").strip()
        pin = (request.args.get("pin") or "").strip()
        sucursal_id = _parse_optional_int(request.args.get("sucursal_id"), "sucursal_id")

        query = GascaSmsRequestORM.query

        if not _is_global_user(user):
            allowed_sucursales = _allowed_sucursales_for_user(user)
            query = query.filter(GascaSmsRequestORM.sucursal_id.in_(allowed_sucursales or [-1]))

        if sucursal_id is not None:
            forbidden = _require_sucursal_access(user, sucursal_id)
            if forbidden:
                return forbidden
            query = query.filter(GascaSmsRequestORM.sucursal_id == sucursal_id)

        if status:
            query = query.filter(GascaSmsRequestORM.status == status)

        if pin:
            query = query.filter(GascaSmsRequestORM.pin_normalized == pin.zfill(5))

        items = (
            query
            .order_by(GascaSmsRequestORM.created_at.desc())
            .limit(limit)
            .all()
        )

        return jsonify({
            "items": [item.to_public_dict() for item in items],
            "count": len(items),
            "limit": limit,
        }), 200

    except ValueError as exc:
        return jsonify({"error": "Bad Request", "detail": str(exc)}), 400


@rpa_gasca_sms_bp.route("/requests/<int:request_id>", methods=["GET"])
@jwt_required()
def get_gasca_sms_request_route(request_id: int):
    user = _get_current_user()
    forbidden = _require_module_access(user)
    if forbidden:
        return forbidden

    item = GascaSmsRequestORM.query.get(request_id)
    if not item:
        return jsonify({"error": "Not Found", "detail": "Solicitud no encontrada."}), 404

    if not _request_visible_for_user(user, item):
        return jsonify({"error": "Forbidden", "detail": "No tienes acceso a esta solicitud."}), 403

    return jsonify({"request": item.to_public_dict()}), 200
