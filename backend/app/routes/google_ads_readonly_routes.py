"""Admin-only live Google Ads API reads; separate from OAuth consent callback."""
from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required

from app.routes.google_ads_oauth_routes import _admin
from app.services.google_ads_readonly_service import (
    GoogleAdsReadError,
    get_campaign_daily,
    verify_account,
)


google_ads_readonly_bp = Blueprint("google_ads_readonly", __name__)


@google_ads_readonly_bp.after_request
def _no_cache(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _read(call):
    if _admin() is None:
        return jsonify({"code": "FORBIDDEN"}), 403
    try:
        return jsonify(call()), 200
    except GoogleAdsReadError as exc:
        # Safe machine-readable codes only. Never return Google API raw body.
        return jsonify({"code": exc.code}), exc.status
    except Exception:
        # No exception or provider payload is included in HTTP/log output.
        current_app.logger.error("Google Ads read request failed unexpectedly.")
        return jsonify({"code": "GOOGLE_ADS_INTERNAL_ERROR"}), 502


@google_ads_readonly_bp.get("/account-check")
@jwt_required()
def google_ads_account_check():
    """Verify actual access to bound target; direct list alone is insufficient for MCC."""
    return _read(verify_account)


@google_ads_readonly_bp.get("/campaign-daily")
@jwt_required()
def google_ads_campaign_daily():
    """Google-attributed daily campaign metrics (never confirmed paid sales)."""
    return _read(
        lambda: get_campaign_daily(
            date_from=request.args.get("date_from"),
            date_to=request.args.get("date_to"),
        )
    )
