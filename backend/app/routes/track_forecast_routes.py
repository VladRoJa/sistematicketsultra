from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import os
from typing import Any
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.routes.track_routes import (
    ALLOWED_GENERATION_MODES,
    _ensure_date,
    _get_current_role,
    _require_track_read_role,
    _resolve_current_track_daily_version_for_query,
    _serialize_decimal,
)
from app.models.user_model import UserORM
from app.models.warehouse import TrackBranchCatalogORM
from app.warehouse.services.track_forecast_center_service import (
    ForecastCenterAuthorizationError,
    ForecastCenterNotFoundError,
    ForecastCenterValidationError,
    build_forecast_center,
    build_forecast_center_catalogs,
)
from app.warehouse.services.track_forecast_service import (
    EXCLUDED_BRANCHES,
    BranchForecastDetailConsistencyError,
    build_branch_forecast_detail,
    build_venta_total_forecast,
)


track_forecast_bp = Blueprint("track_forecast_bp", __name__)


def _get_current_forecast_center_user():
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError) as exc:
        raise PermissionError("No autorizado para consultar el Centro de Forecast.") from exc

    user = UserORM.get_by_id(user_id)
    if user is None:
        raise PermissionError("Usuario no encontrado.")
    return user


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
    role = _get_current_role()

    if role == "LECTOR_GLOBAL":
        return

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


def _resolve_active_forecast_branch(sucursal_canon: str) -> str:
    normalized_branch = str(sucursal_canon or "").strip().upper()
    if not normalized_branch or normalized_branch in EXCLUDED_BRANCHES:
        raise LookupError("La sucursal solicitada no existe o está excluida de Track.")

    row = TrackBranchCatalogORM.query.filter_by(
        sucursal_canon=normalized_branch,
        is_track_active=True,
    ).first()
    if row is None:
        raise LookupError("La sucursal solicitada no existe o está excluida de Track.")
    return str(row.sucursal_canon).strip().upper()


def _serialize_branch_forecast_detail(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _serialize_decimal(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {
            str(key): _serialize_branch_forecast_detail(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_serialize_branch_forecast_detail(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(
        f"Tipo no serializable en detalle de forecast: {type(value).__name__}."
    )


@track_forecast_bp.get("/center/catalogs")
@jwt_required()
def get_forecast_center_catalogs_endpoint():
    try:
        user = _get_current_forecast_center_user()
        requested_track_date = datetime.now(ZoneInfo("America/Tijuana")).date()
        payload = build_forecast_center_catalogs(
            user=user,
            requested_track_date=requested_track_date,
        )
        return jsonify(_serialize_branch_forecast_detail(payload)), 200
    except (PermissionError, ForecastCenterAuthorizationError) as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    except ForecastCenterValidationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:
        return jsonify(
            {
                "status": "error",
                "message": "Falló la consulta de catálogos del Centro de Forecast.",
            }
        ), 500


@track_forecast_bp.get("/center")
@jwt_required()
def get_forecast_center_endpoint():
    try:
        if "view" in request.args or "tab" in request.args:
            raise ForecastCenterValidationError(
                "view y tab no son parámetros de cálculo del Centro de Forecast."
            )

        user = _get_current_forecast_center_user()
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
        scope_id = request.args.get("scope_id")
        cohort = str(request.args.get("cohort") or "all").strip().lower()
        breakdown = request.args.get("breakdown")

        if scope == "branch" and breakdown not in (None, "none"):
            raise ForecastCenterValidationError(
                "scope=branch sólo admite breakdown=none."
            )

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

        payload = build_forecast_center(
            user=user,
            requested_track_date=track_date,
            generation_mode=generation_mode,
            resolved_version=resolved_version,
            scope=scope,
            scope_id=scope_id,
            cohort=cohort,
            breakdown=breakdown,
        )
        return jsonify(_serialize_branch_forecast_detail(payload)), 200
    except (PermissionError, ForecastCenterAuthorizationError) as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    except ForecastCenterNotFoundError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 404
    except (ValueError, ForecastCenterValidationError) as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:
        return jsonify(
            {
                "status": "error",
                "message": "Falló la consulta del Centro de Forecast.",
            }
        ), 500


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


@track_forecast_bp.get("/branches/<string:sucursal_canon>/detail")
@jwt_required()
def get_branch_forecast_detail_endpoint(sucursal_canon: str):
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

        normalized_branch = _resolve_active_forecast_branch(sucursal_canon)
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

        payload = build_branch_forecast_detail(
            sucursal_canon=normalized_branch,
            track_date=track_date,
            generation_mode=generation_mode,
            track_daily_version_id=resolved_version.id,
        )
        payload["metadata"]["resolved_version"] = {
            "id": resolved_version.id,
            "version_type": resolved_version.version_type,
            "status": resolved_version.status,
            "generated_at_utc": resolved_version.generated_at_utc,
            "started_at_utc": resolved_version.started_at_utc,
            "finished_at_utc": resolved_version.finished_at_utc,
        }
        return jsonify(_serialize_branch_forecast_detail(payload)), 200

    except PermissionError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    except LookupError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except BranchForecastDetailConsistencyError:
        return jsonify(
            {
                "status": "error",
                "message": "El detalle de la sucursal es inconsistente con el forecast resuelto.",
            }
        ), 500
    except Exception:
        return jsonify(
            {
                "status": "error",
                "message": "Falló la consulta del detalle de Proyección y Metas.",
            }
        ), 500

@track_forecast_bp.get("/branches")
@jwt_required()
def list_track_forecast_branches():
    _require_track_read_role()
    _require_track_forecast_beta_user()

    rows = (
        TrackBranchCatalogORM.query
        .filter(TrackBranchCatalogORM.is_track_active.is_(True))
        .order_by(
            TrackBranchCatalogORM.display_order.asc(),
            TrackBranchCatalogORM.track_label.asc(),
            TrackBranchCatalogORM.sucursal_canon.asc(),
        )
        .all()
    )

    return jsonify({
        "status": "ok",
        "items": [
            {
                "sucursal_canon": row.sucursal_canon,
                "track_label": row.track_label,
                "display_order": row.display_order,
                "sucursal_id": row.sucursal_id,
            }
            for row in rows
        ],
    })

