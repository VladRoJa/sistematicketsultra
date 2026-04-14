#   backend\app\routes\track_routes.py


from __future__ import annotations

from datetime import date, datetime
from typing import Any

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, jwt_required

from app.warehouse.services.track_daily_pipeline_service import (
    run_track_daily_pipeline_for_date,
)


track_bp = Blueprint("track_bp", __name__)


ALLOWED_GENERATION_MODES = {
    "official_closed_day",
    "manual_preview",
}


def _ensure_date(value: Any, *, field_name: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except Exception as exc:
            raise ValueError(
                f"No se pudo convertir a date el campo {field_name!r}: {value!r}"
            ) from exc

    raise ValueError(f"Valor inválido para {field_name!r}: {value!r}")


def _require_admin_role() -> None:
    claims = get_jwt()
    role = str(claims.get("rol") or "").strip().upper()

    if role not in {"ADMIN", "ADMINISTRADOR", "SUPER_ADMIN"}:
        raise PermissionError("No autorizado para ejecutar el pipeline manual del Track.")


@track_bp.route("/run-daily-pipeline", methods=["POST"])
@jwt_required()
def run_track_daily_pipeline_endpoint():
    try:
        _require_admin_role()

        payload = request.get_json(silent=True) or {}

        track_date = _ensure_date(
            payload.get("track_date"),
            field_name="track_date",
        )

        generation_mode = str(
            payload.get("generation_mode") or "manual_preview"
        ).strip()

        if generation_mode not in ALLOWED_GENERATION_MODES:
            return jsonify(
                {
                    "status": "error",
                    "message": "generation_mode inválido.",
                    "allowed_generation_modes": sorted(ALLOWED_GENERATION_MODES),
                }
            ), 400

        requested_by = str(payload.get("requested_by") or "api_manual_trigger").strip()
        trigger_source = str(payload.get("trigger_source") or "api_track_manual_run").strip()

        result = run_track_daily_pipeline_for_date(
            business_date=track_date,
            generation_mode=generation_mode,
            requested_by=requested_by,
            trigger_source=trigger_source,
        )

        return jsonify(
            {
                "status": "ok",
                "result": result,
            }
        ), 200

    except PermissionError as exc:
        return jsonify(
            {
                "status": "error",
                "message": str(exc),
            }
        ), 403

    except ValueError as exc:
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
                "message": "Falló la ejecución manual del pipeline del Track.",
                "detail": str(exc),
            }
        ), 500