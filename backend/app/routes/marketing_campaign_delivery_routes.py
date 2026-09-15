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
from app.services.marketing_campaign_delivery_service import (
    MarketingCampaignDeliveryConflictError,
    MarketingCampaignDeliveryNotFoundError,
    MarketingCampaignDeliveryValidationError,
    attach_delivery_summaries,
    get_campaign_delivery,
    register_campaign_branch_sends,
)


marketing_campaign_delivery_bp = Blueprint(
    "marketing_campaign_delivery",
    __name__,
)


def _parse_campaign_ids() -> list[int]:
    raw = request.args.get("campaign_ids", "").strip()
    if not raw:
        return []
    values: list[int] = []
    for part in raw.split(","):
        try:
            value = int(part.strip())
        except (TypeError, ValueError) as exc:
            raise MarketingCampaignDeliveryValidationError(
                "campaign_ids debe contener enteros positivos separados por coma."
            ) from exc
        if value <= 0:
            raise MarketingCampaignDeliveryValidationError(
                "campaign_ids debe contener enteros positivos."
            )
        values.append(value)
    return sorted(set(values))


@marketing_campaign_delivery_bp.get(
    "/reactivation/campaigns/delivery-summaries"
)
@jwt_required()
def list_marketing_campaign_delivery_summaries_endpoint():
    try:
        _, access = _resolve_request_access()
        _require_campaign_management(access)
        campaign_ids = _parse_campaign_ids()
        if len(campaign_ids) > 200:
            raise MarketingCampaignDeliveryValidationError(
                "campaign_ids admite como máximo 200 campañas."
            )
        rows = attach_delivery_summaries(
            [{"id": campaign_id} for campaign_id in campaign_ids],
            allowed_sucursal_keys=_reactivation_allowed_sucursal_keys(access),
            session=db.session,
        )
        return jsonify({"rows": rows}), 200
    except MarketingAuthorizationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    except MarketingCampaignDeliveryValidationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:
        return jsonify(
            {"status": "error", "message": "Falló el resumen de envíos por sucursal."}
        ), 500


@marketing_campaign_delivery_bp.get(
    "/reactivation/campaigns/<int:campaign_id>/delivery"
)
@jwt_required()
def get_marketing_campaign_delivery_endpoint(campaign_id: int):
    try:
        _, access = _resolve_request_access()
        _require_campaign_management(access)
        result = get_campaign_delivery(
            campaign_id=campaign_id,
            allowed_sucursal_keys=_reactivation_allowed_sucursal_keys(access),
            session=db.session,
        )
        return jsonify(result), 200
    except MarketingAuthorizationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    except MarketingCampaignDeliveryNotFoundError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 404
    except MarketingCampaignDeliveryValidationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:
        return jsonify(
            {"status": "error", "message": "Falló el detalle de envíos por sucursal."}
        ), 500


@marketing_campaign_delivery_bp.post(
    "/reactivation/campaigns/<int:campaign_id>/delivery"
)
@jwt_required()
def register_marketing_campaign_delivery_endpoint(campaign_id: int):
    try:
        user, access = _resolve_request_access()
        _require_campaign_management(access)
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise MarketingCampaignDeliveryValidationError(
                "El payload JSON debe ser un objeto."
            )
        unknown = sorted(set(payload) - {"sucursales", "sent_at_local"})
        if unknown:
            raise MarketingCampaignDeliveryValidationError(
                "Campos no permitidos: " + ", ".join(unknown) + "."
            )
        result = register_campaign_branch_sends(
            campaign_id=campaign_id,
            sucursales=payload.get("sucursales"),
            sent_at_local=payload.get("sent_at_local"),
            sent_by_user_id=int(user.id),
            allowed_sucursal_keys=_reactivation_allowed_sucursal_keys(access),
            session=db.session,
        )
        return jsonify(result), 200
    except MarketingAuthorizationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    except MarketingCampaignDeliveryNotFoundError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 404
    except MarketingCampaignDeliveryConflictError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 409
    except MarketingCampaignDeliveryValidationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:
        db.session.rollback()
        return jsonify(
            {"status": "error", "message": "Falló el registro de envíos por sucursal."}
        ), 500
