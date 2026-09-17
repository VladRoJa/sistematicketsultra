from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.models.user_model import UserORM
from app.warehouse.services.track_tienda_composition_service import (
    TrackTiendaCompositionServiceError,
    build_track_tienda_composition,
)


track_tienda_bp = Blueprint("track_tienda_bp", __name__)


def _require_admicorp() -> UserORM:
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError) as exc:
        raise PermissionError("No se pudo resolver el usuario actual.") from exc

    user = UserORM.get_by_id(user_id)

    if user is None:
        raise PermissionError("No se pudo resolver el usuario actual.")

    username = str(getattr(user, "username", "") or "").strip().upper()

    if username != "ADMICORP":
        raise PermissionError(
            "La composición de Tienda está habilitada temporalmente solo para ADMICORP."
        )

    return user


def _parse_bool(value: object) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized in {"1", "true", "yes", "si", "sí", "on"}


@track_tienda_bp.route("/tienda-composition", methods=["GET"])
@jwt_required()
def get_track_tienda_composition_endpoint():
    try:
        _require_admicorp()

        result = build_track_tienda_composition(
            track_date=request.args.get("track_date"),
            generation_mode=(
                request.args.get("generation_mode") or "manual_preview"
            ),
            include_operations=_parse_bool(
                request.args.get("include_operations")
            ),
            clave_producto=request.args.get("clave_producto"),
            descripcion=request.args.get("descripcion"),
            sucursal_canon=request.args.get("sucursal_canon"),
            operation_limit=request.args.get("operation_limit"),
        )

        return jsonify(
            {
                "status": "ok",
                **result,
            }
        ), 200

    except PermissionError as exc:
        return jsonify(
            {
                "status": "error",
                "message": str(exc),
            }
        ), 403

    except TrackTiendaCompositionServiceError as exc:
        return jsonify(
            {
                "status": "error",
                "message": str(exc),
            }
        ), 400

    except Exception as exc:
        return jsonify(
            {
                "status": "error",
                "message": "Falló la consulta de composición de Tienda.",
                "detail": str(exc),
            }
        ), 500
