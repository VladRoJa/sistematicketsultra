from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.routes.marketing_routes import (
    _reactivation_allowed_sucursal_keys,
    _require_campaign_management,
    _resolve_request_access,
)
from app.services.marketing_access import MarketingAuthorizationError
from app.services.marketing_campaign_explorer_creation_service import (
    build_explorer_campaign_selection,
    create_campaign_from_explorer,
)
from app.services.marketing_campaign_preview_detail_service import (
    build_marketing_campaign_preview_detail,
)
from app.services.marketing_reactivation_service import (
    MarketingReactivationConflictError,
    MarketingReactivationValidationError,
)


marketing_campaign_preview_detail_bp = Blueprint(
    "marketing_campaign_preview_detail",
    __name__,
)

_COMMON_SELECTION_FIELDS = {
    "bucket",
    "explorer_filters",
    "date_from",
    "date_to",
    "filters",
    "campaign_cooldown_days",
}


def _json_payload() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise MarketingReactivationValidationError(
            "El payload JSON debe ser un objeto."
        )
    return payload


def _reject_unknown_fields(payload: dict, allowed: set[str]) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise MarketingReactivationValidationError(
            "Campos no permitidos: " + ", ".join(unknown) + "."
        )


def _selection_kwargs(payload: dict, access) -> dict:
    return {
        "filters": payload.get("filters"),
        "bucket": payload.get("bucket"),
        "explorer_filters": payload.get("explorer_filters"),
        "date_from": payload.get("date_from"),
        "date_to": payload.get("date_to"),
        "campaign_cooldown_days": payload.get("campaign_cooldown_days"),
        "allowed_sucursal_keys": _reactivation_allowed_sucursal_keys(access),
        "session": db.session,
    }


@marketing_campaign_preview_detail_bp.post(
    "/reactivation/campaigns/preview-detail"
)
@jwt_required()
def marketing_campaign_preview_detail_endpoint():
    try:
        _, access = _resolve_request_access()
        _require_campaign_management(access)
        payload = _json_payload()
        _reject_unknown_fields(
            payload,
            _COMMON_SELECTION_FIELDS | {"page", "page_size"},
        )

        result = build_marketing_campaign_preview_detail(
            page=payload.get("page", 1),
            page_size=payload.get("page_size", 50),
            **_selection_kwargs(payload, access),
        )
        return jsonify(result), 200
    except MarketingAuthorizationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    except MarketingReactivationValidationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:
        return jsonify(
            {
                "status": "error",
                "message": "Falló la consulta del visor de audiencia.",
            }
        ), 500


@marketing_campaign_preview_detail_bp.post(
    "/reactivation/campaigns/preview-detail/selection"
)
@jwt_required()
def marketing_campaign_preview_selection_endpoint():
    try:
        _, access = _resolve_request_access()
        _require_campaign_management(access)
        payload = _json_payload()
        _reject_unknown_fields(payload, _COMMON_SELECTION_FIELDS)
        return jsonify(
            build_explorer_campaign_selection(
                **_selection_kwargs(payload, access),
            )
        ), 200
    except MarketingAuthorizationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    except MarketingReactivationValidationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:
        return jsonify(
            {
                "status": "error",
                "message": "Falló la preparación de la campaña filtrada.",
            }
        ), 500


@marketing_campaign_preview_detail_bp.post(
    "/reactivation/campaigns/preview-detail/create"
)
@jwt_required()
def marketing_campaign_preview_create_endpoint():
    try:
        user, access = _resolve_request_access()
        _require_campaign_management(access)
        payload = _json_payload()
        _reject_unknown_fields(
            payload,
            _COMMON_SELECTION_FIELDS | {"name", "notes"},
        )
        result = create_campaign_from_explorer(
            name=payload.get("name"),
            notes=payload.get("notes"),
            created_by_user_id=int(user.id),
            **_selection_kwargs(payload, access),
        )
        return jsonify(result), 201
    except MarketingAuthorizationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    except MarketingReactivationValidationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except MarketingReactivationConflictError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 409
    except Exception:
        db.session.rollback()
        return jsonify(
            {
                "status": "error",
                "message": "Falló la creación de la campaña filtrada.",
            }
        ), 500
