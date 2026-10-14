"""Google Ads M6: deliberately gated, authenticated initial approval.

No CLI identity overrides, no automatic scheduler integration and no raw data
written by this route. Backend JWT principal and current DB role are checked.
"""
from __future__ import annotations

import os

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required

from app.warehouse.services.google_ads_m6_manual_preview_service import (
    GoogleAdsM6ManualPreviewError,
    MAX_CAMPAIGN_BYTES, MAX_GROUP_BYTES,
    preview_manual_pair, require_current_admicorp,
)

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


@google_ads_m6_continuity_bp.post("/manual/preview")
@jwt_required()
def preview_google_ads_m6_manual_pair():
    """Preview two XLSX without RAW/structured writes or approval."""
    try:
        require_current_admicorp()
    except PermissionError:
        return jsonify({"code": "FORBIDDEN"}), 403
    except Exception:
        current_app.logger.exception("M6 manual preview authorization error.")
        return jsonify({"code": "GOOGLE_ADS_M6_INTERNAL_ERROR"}), 500

    if (request.mimetype != "multipart/form-data"
            or set(request.files) != {"campaign", "ad_group"}
            or bool(request.form)):
        return jsonify({"code": "INVALID_MANUAL_PAIR"}), 400
    if (request.content_length is not None
            and request.content_length > MAX_CAMPAIGN_BYTES + MAX_GROUP_BYTES + 65536):
        return jsonify({"code": "MANUAL_PAIR_TOO_LARGE"}), 413
    content = {}
    for key, limit in (("campaign", MAX_CAMPAIGN_BYTES),
                       ("ad_group", MAX_GROUP_BYTES)):
        file = request.files[key]
        if (not file or not file.filename
                or not file.filename.lower().endswith(".xlsx")):
            return jsonify({"code": "INVALID_XLSX_FILENAME"}), 400
        data = file.stream.read(limit + 1)
        if not data or len(data) > limit:
            return jsonify({"code": "INVALID_XLSX_SIZE"}), 413
        content[key] = data

    try:
        result = preview_manual_pair(
            campaign_bytes=content["campaign"],
            group_bytes=content["ad_group"],
        )
        return jsonify(result), 200
    except GoogleAdsM6ManualPreviewError as exc:
        return jsonify({"status": "REQUIRES_REVIEW", "code": str(exc)}), 422
    except Exception:
        # Never reflect XLSX bodies or filesystem/raw paths in HTTP.
        current_app.logger.warning("M6 manual XLSX preview could not complete.")
        return jsonify({"code": "GOOGLE_ADS_M6_PREVIEW_UNAVAILABLE"}), 503
