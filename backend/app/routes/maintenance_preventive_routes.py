# backend/app/routes/maintenance_preventive_routes.py

from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.extensions import db
from app.models.user_model import UserORM
from app.services.maintenance_preventive_service import (
    MaintenancePreventiveAuthorizationError,
    MaintenancePreventiveError,
    MaintenancePreventiveNotFoundError,
    MaintenancePreventiveStateError,
    actualizar_renglon_lote,
    agregar_renglones_lote,
    crear_lote_preventivo,
    eliminar_renglon_lote,
    listar_lotes_preventivos,
    obtener_lote_preventivo,
    serializar_lote,
    validar_lote_preventivo,
)


maintenance_preventive_bp = Blueprint(
    "maintenance_preventive",
    __name__,
)


def _current_user():
    return UserORM.get_by_id(get_jwt_identity())


def _error_response(exc: Exception):
    if isinstance(exc, MaintenancePreventiveAuthorizationError):
        return jsonify({"mensaje": str(exc)}), 403
    if isinstance(exc, MaintenancePreventiveNotFoundError):
        return jsonify({"mensaje": str(exc)}), 404
    if isinstance(exc, MaintenancePreventiveStateError):
        return jsonify({"mensaje": str(exc)}), 409
    if isinstance(exc, MaintenancePreventiveError):
        return jsonify({"mensaje": str(exc)}), 400
    raise exc


def _batch_summary(batch) -> dict:
    items = list(batch.items or [])
    return {
        "id": batch.id,
        "batch_key": batch.batch_key,
        "nombre": batch.nombre,
        "source_type": batch.source_type,
        "status": batch.status,
        "period_start": (
            batch.period_start.isoformat() if batch.period_start else None
        ),
        "period_end": (
            batch.period_end.isoformat() if batch.period_end else None
        ),
        "created_by_user_id": batch.created_by_user_id,
        "published_at": (
            batch.published_at.isoformat() if batch.published_at else None
        ),
        "total": len(items),
        "validos": sum(
            1 for item in items if item.validation_status == "VALIDO"
        ),
        "errores": sum(
            1 for item in items if item.validation_status == "ERROR"
        ),
        "pendientes": sum(
            1 for item in items if item.validation_status == "PENDIENTE"
        ),
    }


@maintenance_preventive_bp.route("/batches", methods=["GET"])
@jwt_required()
def get_batches():
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        batches = listar_lotes_preventivos(user)
        return jsonify(
            {
                "batches": [
                    _batch_summary(batch)
                    for batch in batches
                ]
            }
        ), 200
    except Exception as exc:
        return _error_response(exc)


@maintenance_preventive_bp.route("/batches", methods=["POST"])
@jwt_required()
def post_batch():
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    payload = request.get_json(silent=True) or {}

    try:
        batch = crear_lote_preventivo(user, payload)
        db.session.commit()
        return jsonify(serializar_lote(batch)), 201
    except Exception as exc:
        db.session.rollback()
        return _error_response(exc)


@maintenance_preventive_bp.route(
    "/batches/<int:batch_id>",
    methods=["GET"],
)
@jwt_required()
def get_batch(batch_id: int):
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        batch = obtener_lote_preventivo(batch_id, user)
        return jsonify(serializar_lote(batch)), 200
    except Exception as exc:
        return _error_response(exc)


@maintenance_preventive_bp.route(
    "/batches/<int:batch_id>/items",
    methods=["POST"],
)
@jwt_required()
def post_batch_items(batch_id: int):
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    payload = request.get_json(silent=True) or {}
    rows = payload.get("items")

    try:
        agregar_renglones_lote(batch_id, user, rows)
        batch = obtener_lote_preventivo(batch_id, user)
        db.session.commit()
        return jsonify(serializar_lote(batch)), 201
    except Exception as exc:
        db.session.rollback()
        return _error_response(exc)


@maintenance_preventive_bp.route(
    "/batches/<int:batch_id>/items/<int:item_id>",
    methods=["PUT"],
)
@jwt_required()
def put_batch_item(batch_id: int, item_id: int):
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    payload = request.get_json(silent=True) or {}

    try:
        item = actualizar_renglon_lote(
            batch_id,
            item_id,
            user,
            payload,
        )
        db.session.commit()
        return jsonify(
            {
                "mensaje": "Renglón actualizado; requiere revalidación.",
                "item": {
                    "id": item.id,
                    "validation_status": item.validation_status,
                },
            }
        ), 200
    except Exception as exc:
        db.session.rollback()
        return _error_response(exc)


@maintenance_preventive_bp.route(
    "/batches/<int:batch_id>/items/<int:item_id>",
    methods=["DELETE"],
)
@jwt_required()
def delete_batch_item(batch_id: int, item_id: int):
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        eliminar_renglon_lote(batch_id, item_id, user)
        db.session.commit()
        return jsonify({"mensaje": "Renglón eliminado."}), 200
    except Exception as exc:
        db.session.rollback()
        return _error_response(exc)


@maintenance_preventive_bp.route(
    "/batches/<int:batch_id>/validate",
    methods=["POST"],
)
@jwt_required()
def post_validate_batch(batch_id: int):
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        summary = validar_lote_preventivo(batch_id, user)
        batch = obtener_lote_preventivo(batch_id, user)
        db.session.commit()
        return jsonify(
            {
                "summary": summary,
                "batch": serializar_lote(batch),
            }
        ), 200
    except Exception as exc:
        db.session.rollback()
        return _error_response(exc)
