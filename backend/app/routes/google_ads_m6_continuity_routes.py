"""Google Ads M6: deliberately gated, authenticated initial approval.

No CLI identity overrides, no automatic scheduler integration and no raw data
written by this route. Backend JWT principal and current DB role are checked.
"""
from __future__ import annotations

import os

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required

from app.warehouse.services.google_ads_m6_continuity_approval_service import (
    M6_REFERENCE,
    approve_authenticated,
)

google_ads_m6_continuity_bp = Blueprint("google_ads_m6_continuity", __name__)
CONFIRMATION = "APROBAR_GOOGLE_ADS_M6_26_SUCURSALES"


@google_ads_m6_continuity_bp.after_request
def _no_cache(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@google_ads_m6_continuity_bp.post("/continuity/approve")
@jwt_required()
def approve_google_ads_m6_continuity():
    """One-time, explicitly confirmed approval, disabled until enabled in env."""
    if os.getenv("GOOGLE_ADS_M6_APPROVAL_ENABLED", "").strip().lower() != "true":
        return jsonify({"code": "GOOGLE_ADS_M6_APPROVAL_DISABLED"}), 503

    if not request.is_json:
        return jsonify({"code": "INVALID_APPROVAL_CONFIRMATION"}), 400
    body = request.get_json(silent=True)
    if (
        not isinstance(body, dict)
        or set(body) != {"approval_reference", "confirmation"}
        or body["approval_reference"] != M6_REFERENCE
        or body["confirmation"] != CONFIRMATION
    ):
        return jsonify({"code": "INVALID_APPROVAL_CONFIRMATION"}), 400

    try:
        result = approve_authenticated()
        return jsonify(result), 200
    except PermissionError:
        return jsonify({"code": "FORBIDDEN"}), 403
    except RuntimeError:
        # Never leak branch identities, upload paths or personal data in HTTP.
        current_app.logger.warning("Google Ads M6 approval preflight rejected.")
        return jsonify({"code": "GOOGLE_ADS_M6_PREFLIGHT_REJECTED"}), 409
    except Exception:
        current_app.logger.exception("Google Ads M6 approval unexpected failure.")
        return jsonify({"code": "GOOGLE_ADS_M6_INTERNAL_ERROR"}), 500
