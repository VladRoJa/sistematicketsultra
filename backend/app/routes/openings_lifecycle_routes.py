from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models import OpeningORM, OpeningStatus, Sucursal, SucursalOperationalStatus
from app.routes.openings_routes import (
    _audit_opening,
    _current_user_id,
    _parse_date,
    _require_openings_admin,
    _serialize_opening,
)
from app.models import OpeningAuditAction


openings_lifecycle_bp = Blueprint("openings_lifecycle_bp", __name__)


_ALLOWED_SOURCE_STATUSES = {
    OpeningStatus.PLANNED,
    OpeningStatus.IN_PROGRESS,
    OpeningStatus.AT_RISK,
    OpeningStatus.PAUSED,
    OpeningStatus.OPENED,
}


@openings_lifecycle_bp.route("/<int:opening_id>/mark-opened", methods=["POST"])
@jwt_required()
def mark_opening_opened(opening_id: int):
    """Marca una apertura como abierta y activa su sucursal atómicamente."""
    denied = _require_openings_admin()
    if denied:
        return denied

    opening = db.session.get(OpeningORM, opening_id)
    if not opening:
        return jsonify({
            "error": "Not Found",
            "detail": "Apertura no encontrada.",
        }), 404

    sucursal = db.session.get(Sucursal, opening.sucursal_id)
    if not sucursal:
        return jsonify({
            "error": "Conflict",
            "detail": "La apertura no tiene una sucursal operativa válida.",
        }), 409

    if opening.status not in _ALLOWED_SOURCE_STATUSES:
        return jsonify({
            "error": "Conflict",
            "detail": "La apertura no puede marcarse como abierta desde su estado actual.",
            "current_status": opening.status,
            "allowed_source_statuses": sorted(_ALLOWED_SOURCE_STATUSES),
        }), 409

    if sucursal.operational_status not in {
        SucursalOperationalStatus.EN_APERTURA,
        SucursalOperationalStatus.ACTIVA,
    }:
        return jsonify({
            "error": "Conflict",
            "detail": "La sucursal no puede activarse desde su estado operativo actual.",
            "current_operational_status": sucursal.operational_status,
        }), 409

    data = request.get_json(silent=True) or {}
    raw_actual_opening_date = data.get("actual_opening_date")

    if not raw_actual_opening_date:
        return jsonify({
            "error": "Bad Request",
            "detail": "actual_opening_date es obligatoria en formato YYYY-MM-DD.",
        }), 400

    try:
        actual_opening_date = _parse_date(raw_actual_opening_date)
    except (TypeError, ValueError):
        return jsonify({
            "error": "Bad Request",
            "detail": "actual_opening_date debe tener formato YYYY-MM-DD.",
        }), 400

    if (
        opening.status == OpeningStatus.OPENED
        and opening.actual_opening_date is not None
        and opening.actual_opening_date != actual_opening_date
    ):
        return jsonify({
            "error": "Conflict",
            "detail": "La apertura ya está abierta con una fecha real distinta.",
            "actual_opening_date": opening.actual_opening_date.isoformat(),
        }), 409

    old_value = _serialize_opening(opening)
    previous_operational_status = sucursal.operational_status

    try:
        opening.status = OpeningStatus.OPENED
        opening.actual_opening_date = actual_opening_date
        opening.updated_by = _current_user_id()
        sucursal.operational_status = SucursalOperationalStatus.ACTIVA

        _audit_opening(
            opening.id,
            OpeningAuditAction.OPENING_UPDATED,
            old_value_json=old_value,
            new_value_json=_serialize_opening(opening),
            metadata_json={
                "transition": "MARK_OPENED",
                "sucursal_id": sucursal.sucursal_id,
                "previous_operational_status": previous_operational_status,
                "new_operational_status": sucursal.operational_status,
            },
        )

        db.session.commit()

        return jsonify({
            "message": "Apertura marcada como abierta y sucursal activada.",
            "item": _serialize_opening(opening),
        }), 200
    except Exception:
        db.session.rollback()
        raise
