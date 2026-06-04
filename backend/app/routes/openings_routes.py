#   backend\app\routes\openings_routes.py


from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    OpeningAuditAction,
    OpeningAuditLogORM,
    OpeningORM,
    OpeningStatus,
    Sucursal,
    SucursalOperationalStatus,
)


openings_bp = Blueprint("openings_bp", __name__)


OPENINGS_ADMIN_ROLES = {
    "ADMIN",
    "ADMINISTRADOR",
    "SUPER_ADMIN",
    "SISTEMAS",
    "APERTURAS_ADMIN",
}

OPENINGS_READ_ROLES = {
    *OPENINGS_ADMIN_ROLES,
    "APERTURAS_MANAGER",
    "APERTURAS_COLABORADOR",
    "APERTURAS_FINANZAS",
    "APERTURAS_LECTOR",
    "GERENTE_REGIONAL",
    "LECTOR_GLOBAL",
}


def _current_role() -> str:
    claims = get_jwt()
    return str(claims.get("rol") or claims.get("role") or "").strip().upper()


def _current_user_id() -> int | None:
    claims = get_jwt()
    raw_user_id = (
        claims.get("user_id")
        or claims.get("id")
        or claims.get("sub_id")
        or get_jwt_identity()
    )

    try:
        return int(raw_user_id)
    except (TypeError, ValueError):
        return None


def _require_openings_read() -> tuple[dict[str, Any], int] | None:
    role = _current_role()

    if role not in OPENINGS_READ_ROLES:
        return jsonify({
            "error": "Forbidden",
            "detail": "No autorizado para consultar Aperturas.",
        }), 403

    return None


def _require_openings_admin() -> tuple[dict[str, Any], int] | None:
    role = _current_role()

    if role not in OPENINGS_ADMIN_ROLES:
        return jsonify({
            "error": "Forbidden",
            "detail": "No autorizado para administrar Aperturas.",
        }), 403

    return None


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None

    if isinstance(value, date):
        return value

    return date.fromisoformat(str(value))


def _parse_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None

    return Decimal(str(value))


def _serialize_decimal(value: Decimal | None) -> float | None:
    if value is None:
        return None

    return float(value)


def _serialize_date(value: date | None) -> str | None:
    if value is None:
        return None

    return value.isoformat()


def _serialize_datetime(value: Any) -> str | None:
    if value is None:
        return None

    return value.isoformat()


def _serialize_user(user: Any) -> dict[str, Any] | None:
    if not user:
        return None

    return {
        "id": getattr(user, "id", None),
        "username": getattr(user, "username", None),
        "rol": getattr(user, "rol", None),
    }


def _serialize_sucursal(sucursal: Sucursal | None) -> dict[str, Any] | None:
    if not sucursal:
        return None

    return {
        "sucursal_id": sucursal.sucursal_id,
        "sucursal": sucursal.sucursal,
        "serie": sucursal.serie,
        "estado": sucursal.estado,
        "municipio": sucursal.municipio,
        "direccion": sucursal.direccion,
        "operational_status": sucursal.operational_status,
    }


def _serialize_opening(opening: OpeningORM) -> dict[str, Any]:
    return {
        "id": opening.id,
        "sucursal_id": opening.sucursal_id,
        "sucursal": _serialize_sucursal(opening.sucursal),
        "opening_key": opening.opening_key,
        "name": opening.name,
        "description": opening.description,
        "status": opening.status,
        "planned_start_date": _serialize_date(opening.planned_start_date),
        "target_opening_date": _serialize_date(opening.target_opening_date),
        "actual_opening_date": _serialize_date(opening.actual_opening_date),
        "general_owner_user_id": opening.general_owner_user_id,
        "general_owner_user": _serialize_user(opening.general_owner_user),
        "budget_authorized_total": _serialize_decimal(opening.budget_authorized_total),
        "budget_currency_code": opening.budget_currency_code,
        "created_by": opening.created_by,
        "updated_by": opening.updated_by,
        "created_at": _serialize_datetime(opening.created_at),
        "updated_at": _serialize_datetime(opening.updated_at),
    }


def _audit_opening(
    opening_id: int,
    action: str,
    *,
    entity_type: str = "OPENING",
    entity_id: int | None = None,
    old_value_json: dict[str, Any] | None = None,
    new_value_json: dict[str, Any] | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> None:
    db.session.add(
        OpeningAuditLogORM(
            opening_id=opening_id,
            entity_type=entity_type,
            entity_id=entity_id or opening_id,
            action=action,
            old_value_json=old_value_json,
            new_value_json=new_value_json,
            metadata_json=metadata_json,
            actor_user_id=_current_user_id(),
        )
    )


@openings_bp.route("", methods=["GET"])
@jwt_required()
def list_openings():
    denied = _require_openings_read()
    if denied:
        return denied

    status = (request.args.get("status") or "").strip().upper()
    q = (request.args.get("q") or "").strip()
    page = request.args.get("page", default=1, type=int) or 1
    page_size = request.args.get("page_size", default=25, type=int) or 25

    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)

    query = OpeningORM.query

    if status and status != "ALL":
        query = query.filter(OpeningORM.status == status)

    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                OpeningORM.opening_key.ilike(like),
                OpeningORM.name.ilike(like),
                OpeningORM.description.ilike(like),
            )
        )

    query = query.order_by(
        OpeningORM.target_opening_date.asc().nullslast(),
        OpeningORM.created_at.desc(),
    )

    pagination = query.paginate(page=page, per_page=page_size, error_out=False)

    return jsonify({
        "items": [_serialize_opening(item) for item in pagination.items],
        "page": pagination.page,
        "page_size": pagination.per_page,
        "total": pagination.total,
        "total_pages": pagination.pages,
        "has_next": pagination.has_next,
        "has_prev": pagination.has_prev,
    }), 200


@openings_bp.route("", methods=["POST"])
@jwt_required()
def create_opening():
    denied = _require_openings_admin()
    if denied:
        return denied

    data = request.get_json(silent=True) or {}

    required_fields = ["sucursal_id", "opening_key", "name"]
    missing = [field for field in required_fields if not data.get(field)]

    if missing:
        return jsonify({
            "error": "Bad Request",
            "detail": "Campos requeridos incompletos.",
            "missing": missing,
        }), 400

    try:
        sucursal_id = int(data["sucursal_id"])
    except (TypeError, ValueError):
        return jsonify({
            "error": "Bad Request",
            "detail": "sucursal_id debe ser entero.",
        }), 400

    sucursal = db.session.get(Sucursal, sucursal_id)

    if not sucursal:
        return jsonify({
            "error": "Not Found",
            "detail": "Sucursal no encontrada.",
        }), 404

    opening_key = str(data["opening_key"]).strip().upper()
    name = str(data["name"]).strip()

    if not opening_key or not name:
        return jsonify({
            "error": "Bad Request",
            "detail": "opening_key y name son obligatorios.",
        }), 400

    try:
        opening = OpeningORM(
            sucursal_id=sucursal_id,
            opening_key=opening_key,
            name=name,
            description=(str(data.get("description")).strip() if data.get("description") else None),
            status=str(data.get("status") or OpeningStatus.DRAFT).strip().upper(),
            planned_start_date=_parse_date(data.get("planned_start_date")),
            target_opening_date=_parse_date(data.get("target_opening_date")),
            actual_opening_date=_parse_date(data.get("actual_opening_date")),
            general_owner_user_id=data.get("general_owner_user_id"),
            budget_authorized_total=_parse_decimal(data.get("budget_authorized_total")),
            budget_currency_code=str(data.get("budget_currency_code") or "MXN").strip().upper(),
            created_by=_current_user_id(),
            updated_by=_current_user_id(),
        )

        if opening.status not in OpeningStatus.ALL:
            return jsonify({
                "error": "Bad Request",
                "detail": "Estado de apertura inválido.",
                "allowed": list(OpeningStatus.ALL),
            }), 400

        db.session.add(opening)
        db.session.flush()

        if sucursal.operational_status != SucursalOperationalStatus.EN_APERTURA:
            sucursal.operational_status = SucursalOperationalStatus.EN_APERTURA

        _audit_opening(
            opening.id,
            OpeningAuditAction.OPENING_CREATED,
            new_value_json=_serialize_opening(opening),
        )

        db.session.commit()

        return jsonify({
            "message": "Apertura creada.",
            "item": _serialize_opening(opening),
        }), 201

    except ValueError as exc:
        db.session.rollback()
        return jsonify({
            "error": "Bad Request",
            "detail": str(exc),
        }), 400
    except IntegrityError:
        db.session.rollback()
        return jsonify({
            "error": "Conflict",
            "detail": "Ya existe una apertura con esa clave.",
        }), 409


@openings_bp.route("/<int:opening_id>", methods=["GET"])
@jwt_required()
def get_opening(opening_id: int):
    denied = _require_openings_read()
    if denied:
        return denied

    opening = db.session.get(OpeningORM, opening_id)

    if not opening:
        return jsonify({
            "error": "Not Found",
            "detail": "Apertura no encontrada.",
        }), 404

    return jsonify({
        "item": _serialize_opening(opening),
    }), 200


@openings_bp.route("/<int:opening_id>", methods=["PATCH"])
@jwt_required()
def update_opening(opening_id: int):
    denied = _require_openings_admin()
    if denied:
        return denied

    opening = db.session.get(OpeningORM, opening_id)

    if not opening:
        return jsonify({
            "error": "Not Found",
            "detail": "Apertura no encontrada.",
        }), 404

    data = request.get_json(silent=True) or {}

    old_value = _serialize_opening(opening)

    try:
        if "name" in data:
            opening.name = str(data.get("name") or "").strip()

        if "description" in data:
            opening.description = (
                str(data.get("description")).strip()
                if data.get("description")
                else None
            )

        if "status" in data:
            next_status = str(data.get("status") or "").strip().upper()

            if next_status not in OpeningStatus.ALL:
                return jsonify({
                    "error": "Bad Request",
                    "detail": "Estado de apertura inválido.",
                    "allowed": list(OpeningStatus.ALL),
                }), 400

            opening.status = next_status

        if "planned_start_date" in data:
            opening.planned_start_date = _parse_date(data.get("planned_start_date"))

        if "target_opening_date" in data:
            opening.target_opening_date = _parse_date(data.get("target_opening_date"))

        if "actual_opening_date" in data:
            opening.actual_opening_date = _parse_date(data.get("actual_opening_date"))

        if "general_owner_user_id" in data:
            opening.general_owner_user_id = data.get("general_owner_user_id")

        if "budget_authorized_total" in data:
            opening.budget_authorized_total = _parse_decimal(data.get("budget_authorized_total"))

        if "budget_currency_code" in data:
            opening.budget_currency_code = str(
                data.get("budget_currency_code") or "MXN"
            ).strip().upper()

        opening.updated_by = _current_user_id()

        _audit_opening(
            opening.id,
            OpeningAuditAction.OPENING_UPDATED,
            old_value_json=old_value,
            new_value_json=_serialize_opening(opening),
        )

        db.session.commit()

        return jsonify({
            "message": "Apertura actualizada.",
            "item": _serialize_opening(opening),
        }), 200

    except ValueError as exc:
        db.session.rollback()
        return jsonify({
            "error": "Bad Request",
            "detail": str(exc),
        }), 400