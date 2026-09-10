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
from app.services.marketing_campaign_preview_detail_service import (
    build_marketing_campaign_preview_detail,
)
from app.services.marketing_reactivation_service import (
    MarketingReactivationValidationError,
)


marketing_campaign_preview_detail_bp = Blueprint(
    "marketing_campaign_preview_detail",
    __name__,
)


@marketing_campaign_preview_detail_bp.post(
    "/reactivation/campaigns/preview-detail"
)
@jwt_required()
def marketing_campaign_preview_detail_endpoint():
    try:
        _, access = _resolve_request_access()
        _require_campaign_management(access)

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise MarketingReactivationValidationError(
                "El payload JSON debe ser un objeto."
            )

        allowed = {
            "bucket",
            "page",
            "page_size",
            "explorer_filters",
            "date_from",
            "date_to",
            "filters",
            "campaign_cooldown_days",
        }
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise MarketingReactivationValidationError(
                "Campos no permitidos: " + ", ".join(unknown) + "."
            )

        result = build_marketing_campaign_preview_detail(
            filters=payload.get("filters"),
            bucket=payload.get("bucket"),
            page=payload.get("page", 1),
            page_size=payload.get("page_size", 50),
            explorer_filters=payload.get("explorer_filters"),
            date_from=payload.get("date_from"),
            date_to=payload.get("date_to"),
            campaign_cooldown_days=payload.get("campaign_cooldown_days"),
            allowed_sucursal_keys=_reactivation_allowed_sucursal_keys(access),
            session=db.session,
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
