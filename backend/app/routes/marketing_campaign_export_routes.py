from __future__ import annotations

from io import BytesIO

from flask import Blueprint, jsonify, send_file
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.routes.marketing_routes import (
    _reactivation_allowed_sucursal_keys,
    _require_campaign_management,
    _resolve_request_access,
)
from app.services.marketing_access import MarketingAuthorizationError
from app.services.marketing_campaign_export_service import (
    campaign_export_mimetype,
    export_marketing_reactivation_campaign,
)
from app.services.marketing_reactivation_service import (
    MarketingReactivationConflictError,
    MarketingReactivationInvalidTransitionError,
    MarketingReactivationNotFoundError,
    MarketingReactivationValidationError,
)


marketing_campaign_export_bp = Blueprint(
    "marketing_campaign_export",
    __name__,
)


@marketing_campaign_export_bp.get(
    "/reactivation/campaigns/<int:campaign_id>/export-package"
)
@jwt_required()
def export_marketing_campaign_package_endpoint(campaign_id: int):
    try:
        _, access = _resolve_request_access()
        _require_campaign_management(access)
        file_bytes, filename = export_marketing_reactivation_campaign(
            campaign_id=campaign_id,
            allowed_sucursal_keys=_reactivation_allowed_sucursal_keys(access),
            session=db.session,
        )
        return send_file(
            BytesIO(file_bytes),
            as_attachment=True,
            download_name=filename,
            mimetype=campaign_export_mimetype(filename),
        )
    except MarketingAuthorizationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    except MarketingReactivationNotFoundError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 404
    except (
        MarketingReactivationConflictError,
        MarketingReactivationInvalidTransitionError,
    ) as exc:
        return jsonify({"status": "error", "message": str(exc)}), 409
    except MarketingReactivationValidationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:
        db.session.rollback()
        return jsonify(
            {"status": "error", "message": "Falló la exportación de la campaña."}
        ), 500
