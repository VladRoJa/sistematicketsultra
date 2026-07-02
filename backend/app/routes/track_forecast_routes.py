from __future__ import annotations

import os

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.routes.track_routes import (
    ALLOWED_GENERATION_MODES,
    _ensure_date,
    _require_track_read_role,
    _resolve_current_track_daily_version_for_query,
)
from app.warehouse.services.track_forecast_service import (
    build_venta_total_forecast,
)


track_forecast_bp = Blueprint("track_forecast_bp", __name__)


def _get_forecast_beta_user_ids() -> set[int]:
    raw_value = os.environ.get("TRACK_FORECAST_BETA_USER_IDS", "").strip()

    if not raw_value:
        return set()

    user_ids: set[int] = set()

    for raw_part in raw_value.split(","):
        part = raw_part.strip()

        if not part:
            continue

        try:
            user_ids.add(int(part))
        except ValueError as exc:
            raise ValueError(
                "TRACK_FORECAST_BETA_USER_IDS debe contener solo IDs numéricos separados por coma."
            ) from exc

    return user_ids


def _require_track_forecast_beta_user() -> None:
    allowed_user_ids = _get_forecast_beta_user_ids()

    if not allowed_user_ids:
        raise PermissionError(
            "Proyección y Metas está en beta privada y no tiene usuarios habilitados."
        )

    try:
        current_user_id = int(get_jwt_identity())
    except (TypeError, ValueError) as exc:
        raise PermissionError("No autorizado para consultar Proyección y Metas.") from exc

    if current_user_id not in allowed_user_ids:
        raise PermissionError("No autorizado para consultar Proyección y Metas.")


@track_forecast_bp.route("/venta-total", methods=["GET"])
@jwt_required()
def get_venta_total_forecast_endpoint():
    try:
        _require_track_read_role()
        _require_track_forecast_beta_user()

        track_date = _ensure_date(
            request.args.get("track_date"),
            field_name="track_date",
        )

        generation_mode = str(
            request.args.get("generation_mode") or "manual_preview"
        ).strip()

        if generation_mode not in ALLOWED_GENERATION_MODES:
            return jsonify(
                {
                    "status": "error",
                    "message": "generation_mode inválido.",
                    "allowed_generation_modes": sorted(ALLOWED_GENERATION_MODES),
                }
            ), 400

        scope = str(request.args.get("scope") or "national").strip().lower()
        branch = request.args.get("branch")

        resolved_version = _resolve_current_track_daily_version_for_query(
            track_date=track_date,
            generation_mode=generation_mode,
        )

        if resolved_version is None:
            return jsonify(
                {
                    "status": "error",
                    "message": "No existe versión Track disponible para la fecha/modo solicitados.",
                    "track_date": track_date.isoformat(),
                    "generation_mode": generation_mode,
                }
            ), 404

        payload = build_venta_total_forecast(
            track_date=track_date,
            generation_mode=generation_mode,
            track_daily_version_id=resolved_version.id,
            scope=scope,
            branch=branch,
        )

        payload["metadata"]["resolved_version"] = {
            "id": resolved_version.id,
            "version_type": resolved_version.version_type,
            "status": resolved_version.status,
            "generated_at_utc": (
                resolved_version.generated_at_utc.isoformat()
                if resolved_version.generated_at_utc
                else None
            ),
            "started_at_utc": (
                resolved_version.started_at_utc.isoformat()
                if resolved_version.started_at_utc
                else None
            ),
            "finished_at_utc": (
                resolved_version.finished_at_utc.isoformat()
                if resolved_version.finished_at_utc
                else None
            ),
        }

        return jsonify(payload), 200

    except PermissionError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403

    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    except Exception as exc:
        return jsonify(
            {
                "status": "error",
                "message": "Falló la consulta de Proyección y Metas.",
                "detail": str(exc),
            }
        ), 500
