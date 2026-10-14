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
from app.warehouse.services.google_ads_m6_manual_confirm_service import (
    GoogleAdsM6ManualConfirmError, issue_raw_confirmation_ticket,
    confirm_google_ads_m6_manual_pair,
)
from app.utils.warehouse_access import require_warehouse_upload

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
        actor_id = require_current_admicorp()
    except PermissionError:
        return jsonify({"code": "FORBIDDEN"}), 403
    except Exception:
        current_app.logger.exception("M6 manual preview authorization error.")
        return jsonify({"code": "GOOGLE_ADS_M6_INTERNAL_ERROR"}), 500

    # Check total size *before* request.files parses multipart content.
    # Per-file stream limits below remain mandatory for missing length headers.
    if (request.content_length is not None
            and request.content_length > MAX_CAMPAIGN_BYTES + MAX_GROUP_BYTES + 65536):
        return jsonify({"code": "MANUAL_PAIR_TOO_LARGE"}), 413
    if (request.mimetype != "multipart/form-data"
            or set(request.files) != {"campaign", "ad_group"}
            or bool(request.form)):
        return jsonify({"code": "INVALID_MANUAL_PAIR"}), 400
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
        result["raw_confirm_ticket"] = issue_raw_confirmation_ticket(
            result, actor_id=actor_id,
        )
        result["ready_to_stage_raw"] = True
        return jsonify(result), 200
    except GoogleAdsM6ManualPreviewError as exc:
        return jsonify({"status": "REQUIRES_REVIEW", "code": str(exc)}), 422
    except Exception:
        # Never reflect XLSX bodies or filesystem/raw paths in HTTP.
        current_app.logger.warning("M6 manual XLSX preview could not complete.")
        return jsonify({"code": "GOOGLE_ADS_M6_PREVIEW_UNAVAILABLE"}), 503


@google_ads_m6_continuity_bp.post("/manual/confirm")
@jwt_required()
def confirm_google_ads_m6_manual_raw():
    """Authenticated, ticket-bound paired RAW staging. Never auto-publish."""
    try:
        actor_id = require_current_admicorp()
    except PermissionError:
        return jsonify({"code": "FORBIDDEN"}), 403
    except Exception:
        return jsonify({"code": "GOOGLE_ADS_M6_INTERNAL_ERROR"}), 500

    denied = require_warehouse_upload()
    if denied:
        return denied
    # Never parse a huge multipart message just to reject it.
    if (request.content_length is not None
            and request.content_length >
            MAX_CAMPAIGN_BYTES + MAX_GROUP_BYTES + 69632):
        return jsonify({"code": "MANUAL_PAIR_TOO_LARGE"}), 413
    if (request.mimetype != "multipart/form-data"
            or set(request.files) != {"campaign", "ad_group"}
            or set(request.form) != {"confirmation_ticket"}):
        return jsonify({"code": "INVALID_MANUAL_CONFIRMATION"}), 400

    ticket = request.form["confirmation_ticket"]
    if not 0 < len(ticket) <= 4096:
        return jsonify({"code": "INVALID_CONFIRMATION_TICKET"}), 400

    data = {}
    for name, limit in (("campaign", MAX_CAMPAIGN_BYTES),
                        ("ad_group", MAX_GROUP_BYTES)):
        part = request.files[name]
        if not part or not part.filename or not part.filename.lower().endswith(".xlsx"):
            return jsonify({"code": "INVALID_XLSX_FILENAME"}), 400
        value = part.stream.read(limit + 1)
        if not value or len(value) > limit:
            return jsonify({"code": "INVALID_XLSX_SIZE"}), 413
        data[name] = value

    try:
        result = confirm_google_ads_m6_manual_pair(
            actor_id=actor_id, ticket=ticket,
            campaign_bytes=data["campaign"],
            group_bytes=data["ad_group"],
        )
    except GoogleAdsM6ManualConfirmError as exc:
        return jsonify({"status": "REQUIRES_REVIEW", "code": str(exc)}), 409
    except Exception:
        # Do not echo upload contents or exception strings in logs/response.
        current_app.logger.warning("M6 paired manual RAW stage unavailable.")
        return jsonify({"code": "M6_RAW_STAGE_UNAVAILABLE"}), 503

    if result["status"] != "RAW_PAIR_STAGED":
        return jsonify(result), 409
    if all(item["reused_existing"] for item in result["uploads"].values()):
        return jsonify(result), 200
    return jsonify(result), 201
