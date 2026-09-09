from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.routes.marketing_routes import _require_campaign_management, _resolve_request_access
from app.services.marketing_access import MarketingAuthorizationError
from app.services.marketing_campaign_source_status_service import read_campaign_source_status


marketing_campaign_source_status_bp = Blueprint(
    "marketing_campaign_source_status",
    __name__,
)


@marketing_campaign_source_status_bp.get("/reactivation/campaigns/source-status")
@jwt_required()
def marketing_campaign_source_status_endpoint():
    try:
        _, access = _resolve_request_access()
        _require_campaign_management(access)
        return jsonify(read_campaign_source_status(session=db.session)), 200
    except MarketingAuthorizationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    except Exception:
        return jsonify(
            {"status": "error", "message": "No fue posible consultar las fuentes de audiencia."}
        ), 500
