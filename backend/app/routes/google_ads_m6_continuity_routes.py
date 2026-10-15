"""Google Ads M6: deliberately gated, authenticated initial approval.

No CLI identity overrides, no automatic scheduler integration and no raw data
written by this route. Backend JWT principal and current DB role are checked.
"""
from __future__ import annotations

import os

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required
from app.extensions import db

from app.warehouse.services.google_ads_m6_manual_preview_service import (
    GoogleAdsM6ManualPreviewError,
    MAX_CAMPAIGN_BYTES, MAX_GROUP_BYTES,
    preview_manual_pair, require_current_admicorp,
)
from app.warehouse.services.google_ads_m6_correction_candidate_service import (
    FLAG as CORRECTION_CANDIDATE_FLAG,
    stage_m6_correction_candidate, GoogleAdsM6CorrectionStageError,
)
from app.warehouse.services.google_ads_m6_correction_promotion_service import (
    promote_m6_correction, GoogleAdsM6CorrectionPromotionError,
    FLAG as CORRECTION_PROMOTION_FLAG,
)
from app.warehouse.services.google_ads_m6_correction_decision_service import (
    decide_m6_correction, GoogleAdsM6CorrectionDecisionError,
    _current_correction_permissions,
    FLAG as CORRECTION_REVIEW_FLAG,
)
from app.warehouse.services.google_ads_m6_correction_review_service import (
    inspect_correction_case, GoogleAdsM6CorrectionReviewError,
)
from app.warehouse.services.google_ads_m6_correction_raw_service import (
    GoogleAdsM6CorrectionRawError, FLAG as CORRECTION_RAW_FLAG,
    preview_correction_raw_pair, confirm_correction_raw_pair,
)
from app.warehouse.services.google_ads_m6_manual_confirm_service import (
    GoogleAdsM6ManualConfirmError, issue_raw_confirmation_ticket,
    confirm_google_ads_m6_manual_pair,
)
from app.utils.warehouse_access import require_warehouse_view
from app.warehouse.services.google_ads_m6_manual_correction_diagnostic_service import inspect_m6_day_for_correction
from app.utils.warehouse_access import require_warehouse_upload
from app.warehouse.services.google_ads_m6_manual_publication_service import (
    CONFIRMATION as PUBLICATION_CONFIRMATION,
    publish_manual_daily_pair,
)
from app.warehouse.services.google_ads_m6_manual_structured_service import (
    CONFIRMATION as STRUCTURED_CONFIRMATION,
    GoogleAdsM6ManualStructuredError,
    stage_structured_manual_pair,
)

from app.warehouse.services.google_ads_m6_continuity_approval_service import (
    CUSTOMER_ID, M6_REFERENCE,
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


@google_ads_m6_continuity_bp.post("/manual/ingest")
@jwt_required()
def ingest_google_ads_m6_structured_pair():
    """Explicit atomic structured stage. Raw confirmation never calls this."""
    if os.getenv("GOOGLE_ADS_M6_STRUCTURED_INGESTION_ENABLED", "").strip().lower() != "true":
        return jsonify({"code": "M6_STRUCTURED_INGESTION_DISABLED"}), 503
    try:
        actor_id = require_current_admicorp()
    except PermissionError:
        return jsonify({"code": "FORBIDDEN"}), 403
    except Exception:
        return jsonify({"code": "GOOGLE_ADS_M6_INTERNAL_ERROR"}), 500
    denied = require_warehouse_upload()
    if denied:
        return denied
    if not request.is_json or (request.content_length or 0) > 4096:
        return jsonify({"code": "INVALID_STRUCTURED_REQUEST"}), 400
    data = request.get_json(silent=True)
    if (not isinstance(data, dict)
            or set(data) != {"campaign_upload_id", "ad_group_upload_id", "confirmation"}
            or data["confirmation"] != STRUCTURED_CONFIRMATION
            or type(data["campaign_upload_id"]) is not int
            or type(data["ad_group_upload_id"]) is not int
            or data["campaign_upload_id"] <= 0
            or data["ad_group_upload_id"] <= 0
            or data["campaign_upload_id"] == data["ad_group_upload_id"]):
        return jsonify({"code": "INVALID_STRUCTURED_REQUEST"}), 400
    try:
        result = stage_structured_manual_pair(
            actor_id=actor_id,
            campaign_upload_id=data["campaign_upload_id"],
            group_upload_id=data["ad_group_upload_id"],
        )
        return jsonify(result), 200 if result["status"] == "ALREADY_INGESTED" else 201
    except GoogleAdsM6ManualStructuredError as exc:
        status = 403 if str(exc) == "FORBIDDEN" else 409
        return jsonify({"code": str(exc), "eligible_for_publication": False}), status
    except Exception:
        current_app.logger.exception("M6 atomic structured stage rolled back.")
        return jsonify({"code": "M6_STRUCTURED_STAGE_FAILED"}), 503



@google_ads_m6_continuity_bp.post("/manual/publish")
@jwt_required()
def publish_google_ads_m6_manual_day():
    """Explicit canonical publication, never invoked by RAW/ingest."""
    if os.getenv("GOOGLE_ADS_M6_DAILY_PUBLICATION_ENABLED", "").strip().lower() != "true":
        return jsonify({"code": "M6_DAILY_PUBLICATION_DISABLED"}), 503
    try:
        actor_id = require_current_admicorp()
    except PermissionError:
        return jsonify({"code": "FORBIDDEN"}), 403
    except Exception:
        current_app.logger.exception("M6 publication authorization failure.")
        return jsonify({"code": "GOOGLE_ADS_M6_INTERNAL_ERROR"}), 500
    denied = require_warehouse_upload()
    if denied:
        return denied
    if not request.is_json or (request.content_length or 0) > 4096:
        return jsonify({"code": "INVALID_PUBLICATION_REQUEST"}), 400
    body = request.get_json(silent=True)
    if (not isinstance(body, dict)
            or set(body) != {"campaign_upload_id", "ad_group_upload_id", "confirmation"}
            or body["confirmation"] != PUBLICATION_CONFIRMATION
            or type(body["campaign_upload_id"]) is not int
            or type(body["ad_group_upload_id"]) is not int
            or body["campaign_upload_id"] <= 0
            or body["ad_group_upload_id"] <= 0
            or body["campaign_upload_id"] == body["ad_group_upload_id"]):
        return jsonify({"code": "INVALID_PUBLICATION_REQUEST"}), 400
    try:
        result = publish_manual_daily_pair(
            actor_id=actor_id,
            campaign_upload_id=body["campaign_upload_id"],
            group_upload_id=body["ad_group_upload_id"],
        )
        return jsonify(result), 200 if result["status"] == "ALREADY_PUBLISHED" else 201
    except GoogleAdsM6ManualStructuredError as exc:
        code = str(exc)
        return jsonify({"code": code}), 403 if code == "FORBIDDEN" else 409
    except Exception:
        current_app.logger.exception("M6 canonical daily publication aborted.")
        return jsonify({"code": "M6_PUBLICATION_FAILED"}), 503



@google_ads_m6_continuity_bp.get("/manual/correction-status")
@jwt_required()
def google_ads_m6_manual_correction_status():
    """ADMICORP-only, read-only day inspection; no archival or correction."""
    from datetime import date
    import re

    try:
        require_current_admicorp()
    except PermissionError:
        return jsonify({"code": "FORBIDDEN"}), 403
    except Exception:
        current_app.logger.exception("Google Ads M6 correction diagnostic auth error.")
        return jsonify({"code": "GOOGLE_ADS_M6_INTERNAL_ERROR"}), 500
    denied = require_warehouse_view()
    if denied:
        return denied
    if set(request.args.keys()) != {"day"}:
        return jsonify({"code": "INVALID_CORRECTION_DAY"}), 400
    raw_day = request.args.get("day", "")
    if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", raw_day):
        return jsonify({"code": "INVALID_CORRECTION_DAY"}), 400
    try:
        selected = date.fromisoformat(raw_day)
        if selected < date(2026, 10, 13):
            return jsonify({"code": "INVALID_CORRECTION_DAY"}), 400
        return jsonify(inspect_m6_day_for_correction(business_date=selected)), 200
    except ValueError:
        return jsonify({"code": "INVALID_CORRECTION_DAY"}), 400
    except Exception:
        current_app.logger.exception("M6 correction day diagnostic failed.")
        return jsonify({"code": "M6_CORRECTION_DIAGNOSTIC_UNAVAILABLE"}), 503


@google_ads_m6_continuity_bp.post("/corrections/raw/preview")
@jwt_required()
def preview_m6_correction_raw():
    """Explicit correction-only preflight; separate from daily normal upload."""
    if os.getenv(CORRECTION_RAW_FLAG, "").strip().lower() != "true":
        return jsonify({"code": "CORRECTION_RAW_DISABLED"}), 503
    try:
        actor_id = require_current_admicorp()
    except PermissionError:
        return jsonify({"code": "FORBIDDEN"}), 403
    denied = require_warehouse_upload()
    if denied:
        return denied
    if (request.content_length is not None
            and request.content_length > MAX_CAMPAIGN_BYTES + MAX_GROUP_BYTES + 69632):
        return jsonify({"code": "CORRECTION_FILES_TOO_LARGE"}), 413
    if (request.mimetype != "multipart/form-data"
            or set(request.files) != {"campaign", "ad_group"}
            or set(request.form) != {"reason"}):
        return jsonify({"code": "INVALID_CORRECTION_REQUEST"}), 400
    content = {}
    for name, limit in (("campaign", MAX_CAMPAIGN_BYTES),
                        ("ad_group", MAX_GROUP_BYTES)):
        part = request.files[name]
        if not part or not part.filename or not part.filename.lower().endswith(".xlsx"):
            return jsonify({"code": "INVALID_CORRECTION_FILENAME"}), 400
        content[name] = part.stream.read(limit + 1)
        if not 0 < len(content[name]) <= limit:
            return jsonify({"code": "INVALID_CORRECTION_SIZE"}), 413
    try:
        output = preview_correction_raw_pair(
            actor_id=actor_id,
            campaign_bytes=content["campaign"], group_bytes=content["ad_group"],
            reason=request.form["reason"])
        return jsonify(output), 200
    except GoogleAdsM6CorrectionRawError as exc:
        return jsonify({"code": str(exc), "eligible_for_publication": False}), 409
    except Exception:
        current_app.logger.exception("M6 correction RAW preview rejected.")
        return jsonify({"code": "CORRECTION_PREVIEW_UNAVAILABLE"}), 503


@google_ads_m6_continuity_bp.post("/corrections/raw/confirm")
@jwt_required()
def confirm_m6_correction_raw():
    """Ticket bound to actor and two files; does not publish or ingest facts."""
    if os.getenv(CORRECTION_RAW_FLAG, "").strip().lower() != "true":
        return jsonify({"code": "CORRECTION_RAW_DISABLED"}), 503
    try:
        actor_id = require_current_admicorp()
    except PermissionError:
        return jsonify({"code": "FORBIDDEN"}), 403
    denied = require_warehouse_upload()
    if denied:
        return denied
    if (request.content_length is not None
            and request.content_length > MAX_CAMPAIGN_BYTES + MAX_GROUP_BYTES + 69632):
        return jsonify({"code": "CORRECTION_FILES_TOO_LARGE"}), 413
    if (request.mimetype != "multipart/form-data"
            or set(request.files) != {"campaign", "ad_group"}
            or set(request.form) != {"correction_ticket"}):
        return jsonify({"code": "INVALID_CORRECTION_REQUEST"}), 400
    ticket = request.form["correction_ticket"]
    if not 0 < len(ticket) <= 4096:
        return jsonify({"code": "INVALID_CORRECTION_CONFIRMATION"}), 400
    content = {}
    for name, limit in (("campaign", MAX_CAMPAIGN_BYTES),
                        ("ad_group", MAX_GROUP_BYTES)):
        part = request.files[name]
        if not part or not part.filename or not part.filename.lower().endswith(".xlsx"):
            return jsonify({"code": "INVALID_CORRECTION_FILENAME"}), 400
        content[name] = part.stream.read(limit + 1)
        if not 0 < len(content[name]) <= limit:
            return jsonify({"code": "INVALID_CORRECTION_SIZE"}), 413
    try:
        output = confirm_correction_raw_pair(
            actor_id=actor_id, ticket=ticket,
            campaign_bytes=content["campaign"], group_bytes=content["ad_group"])
        if output["status"] != "CORRECTION_RAW_PAIR_STAGED":
            return jsonify(output), 409
        return jsonify(output), (
            200 if all(u["reused_existing"] for u in output["uploads"].values())
            else 201
        )
    except GoogleAdsM6CorrectionRawError as exc:
        return jsonify({"code": str(exc), "eligible_for_publication": False}), 409
    except Exception:
        current_app.logger.exception("M6 correction RAW confirmation failed.")
        return jsonify({"code": "CORRECTION_RAW_STAGE_UNAVAILABLE"}), 503


@google_ads_m6_continuity_bp.post("/corrections/candidates/ingest")
@jwt_required()
def ingest_m6_correction_candidate():
    """Explicit candidate-only staging; cannot publish or replace canonical."""
    if os.getenv(CORRECTION_CANDIDATE_FLAG, "").strip().lower() != "true":
        return jsonify({"code": "CORRECTION_CANDIDATE_DISABLED"}), 503
    try:
        require_current_admicorp()
    except PermissionError:
        return jsonify({"code": "FORBIDDEN"}), 403
    denied = require_warehouse_upload()
    if denied:
        return denied
    if not request.is_json or (request.content_length or 0) > 2048:
        return jsonify({"code": "INVALID_CORRECTION_CANDIDATE"}), 400
    body = request.get_json(silent=True)
    if (not isinstance(body, dict) or set(body) != {
            "campaign_upload_id", "ad_group_upload_id", "revision",
            "expected_publication_id", "reason", "confirmation"
        } or body.get("confirmation") != "INGESTAR_CORRECCION_M6_SIN_PUBLICAR"
        or any(type(body.get(k)) is not int or body[k] <= 0
               for k in ("campaign_upload_id", "ad_group_upload_id", "revision"))
        or (body["expected_publication_id"] is not None and (
            type(body["expected_publication_id"]) is not int
            or body["expected_publication_id"] <= 0))
        or not isinstance(body["reason"], str)
        or not 10 <= len(body["reason"].strip()) <= 500):
        return jsonify({"code": "INVALID_CORRECTION_CANDIDATE"}), 400
    try:
        result = stage_m6_correction_candidate(
            campaign_upload_id=body["campaign_upload_id"],
            group_upload_id=body["ad_group_upload_id"],
            revision=body["revision"], reason=body["reason"],
            expected_publication_id=body["expected_publication_id"],
        )
        return jsonify(result), 200 if result["status"] == "ALREADY_STAGED" else 201
    except GoogleAdsM6CorrectionStageError as exc:
        return jsonify({"code": str(exc), "eligible_for_publication": False}), (
            403 if str(exc) == "FORBIDDEN" else 409
        )
    except Exception:
        current_app.logger.exception("M6 correction candidate staging aborted.")
        return jsonify({"code": "CORRECTION_CANDIDATE_STAGE_UNAVAILABLE"}), 503


@google_ads_m6_continuity_bp.get("/corrections/candidates/<int:case_id>")
@jwt_required()
def get_m6_correction_candidate(case_id):
    """ADMICORP-only, READ ONLY financial diff; NEVER grants approval."""
    if not _current_correction_permissions()["can_read"]:
        return jsonify({"code": "FORBIDDEN"}), 403
    try:
        return jsonify(inspect_correction_case(case_id)), 200
    except GoogleAdsM6CorrectionReviewError as exc:
        return jsonify({"code": str(exc)}), 404
    except Exception:
        current_app.logger.exception("M6 candidate review unavailable.")
        return jsonify({"code": "CORRECTION_CASE_REVIEW_UNAVAILABLE"}), 503


@google_ads_m6_continuity_bp.post("/corrections/candidates/<int:case_id>/review")
@jwt_required()
def review_m6_correction_candidate(case_id):
    """Allowlisted independent reviewer. Does not grant canonical publication."""
    if os.getenv(CORRECTION_REVIEW_FLAG, "").strip().lower() != "true":
        return jsonify({"code": "CORRECTION_REVIEW_DISABLED"}), 503
    denied = require_warehouse_view()
    if denied:
        return denied
    if not request.is_json or (request.content_length or 0) > 1400:
        return jsonify({"code": "INVALID_CORRECTION_DECISION"}), 400
    body = request.get_json(silent=True)
    if (not isinstance(body, dict)
            or set(body) != {"decision", "note", "confirmation"}
            or body.get("confirmation") != "REVISION_INDEPENDIENTE_SIN_PUBLICAR"
            or body.get("decision") not in ("APPROVED", "REJECTED")
            or not isinstance(body.get("note"), str)
            or not 10 <= len(body["note"].strip()) <= 1000):
        return jsonify({"code": "INVALID_CORRECTION_DECISION"}), 400
    try:
        output = decide_m6_correction(
            case_id=case_id, decision=body["decision"], note=body["note"])
        return jsonify(output), (200 if output["status"] == "ALREADY_REVIEWED"
                                  else 201)
    except GoogleAdsM6CorrectionDecisionError as exc:
        code = str(exc)
        return jsonify({"code": code, "eligible_for_publication": False}), (
            403 if code in ("FORBIDDEN", "CORRECTION_SELF_REVIEW_FORBIDDEN")
            else 404 if code == "CORRECTION_CASE_NOT_FOUND" else 409
        )
    except Exception:
        current_app.logger.exception("Independent M6 correction review rejected")
        return jsonify({"code": "CORRECTION_REVIEW_UNAVAILABLE"}), 503


@google_ads_m6_continuity_bp.post("/corrections/candidates/<int:case_id>/promote")
@jwt_required()
def promote_m6_correction_candidate(case_id):
    """Explicit, independently approved revision, never an upload side effect."""
    if os.getenv(CORRECTION_PROMOTION_FLAG, "").strip().lower() != "true":
        return jsonify({"code": "CORRECTION_PROMOTION_DISABLED"}), 503
    try:
        require_current_admicorp()
    except PermissionError:
        return jsonify({"code": "FORBIDDEN"}), 403
    denied = require_warehouse_upload()
    if denied:
        return denied
    if not request.is_json or (request.content_length or 0) > 1024:
        return jsonify({"code": "INVALID_CORRECTION_PROMOTION"}), 400
    data = request.get_json(silent=True)
    if (not isinstance(data, dict)
        or set(data) != {
            "decision_id", "snapshot_sha256", "revision",
            "expected_publication_id", "confirmation",
        }
        or data.get("confirmation") != "PUBLICAR_REVISION_GOOGLE_ADS_M6"
        or any(type(data.get(k)) is not int or data[k] <= 0
               for k in ("decision_id", "revision"))
        or (data.get("expected_publication_id") is not None and
            (type(data["expected_publication_id"]) is not int
             or data["expected_publication_id"] <= 0))
        or not isinstance(data.get("snapshot_sha256"), str)):
        return jsonify({"code": "INVALID_CORRECTION_PROMOTION"}), 400
    try:
        result = promote_m6_correction(
            case_id=case_id, decision_id=data["decision_id"],
            snapshot_sha256=data["snapshot_sha256"],
            revision=data["revision"],
            expected_publication_id=data["expected_publication_id"],
        )
        return jsonify(result), (
            200 if result["status"] == "ALREADY_PROMOTED" else 201
        )
    except GoogleAdsM6CorrectionPromotionError as exc:
        code = str(exc)
        return jsonify({"code": code}), (403 if code == "FORBIDDEN" else 409)
    except Exception:
        current_app.logger.exception("M6 correction promotion rolled back.")
        return jsonify({"code": "CORRECTION_PROMOTION_UNAVAILABLE"}), 503


@google_ads_m6_continuity_bp.get("/corrections/capabilities")
@jwt_required()
def m6_correction_capabilities():
    """Current principal's server-side capabilities; safe for non-ADMICORP admins."""
    return jsonify(_current_correction_permissions()), 200


@google_ads_m6_continuity_bp.get("/corrections/candidates")
@jwt_required()
def list_m6_correction_candidates():
    """Bounded, authorized listing; no global financial detail in this response."""
    if not _current_correction_permissions()["can_read"]:
        return jsonify({"code": "FORBIDDEN"}), 403
    day = request.args.get("day", "", type=str)
    if day and not (len(day) == 10 and day >= "2026-10-13"):
        return jsonify({"code": "INVALID_CORRECTION_DAY"}), 400
    try:
        from app.models.google_ads_m6_correction import GoogleAdsM6CorrectionCaseORM
        from app.models.google_ads_m6_correction_decision import GoogleAdsM6CorrectionDecisionORM
        query = db.session.query(GoogleAdsM6CorrectionCaseORM,
                                 GoogleAdsM6CorrectionDecisionORM).outerjoin(
            GoogleAdsM6CorrectionDecisionORM,
            GoogleAdsM6CorrectionDecisionORM.case_id ==
                GoogleAdsM6CorrectionCaseORM.id,
        ).filter(GoogleAdsM6CorrectionCaseORM.customer_id == CUSTOMER_ID)
        if day:
            from datetime import date
            query = query.filter(
                GoogleAdsM6CorrectionCaseORM.business_date ==
                date.fromisoformat(day),
            )
        cases = query.order_by(
            GoogleAdsM6CorrectionCaseORM.business_date.desc(),
            GoogleAdsM6CorrectionCaseORM.revision.desc(),
        ).limit(50).all()
        return jsonify({
            "cases": [{
                "case_id": case.id, "business_date": case.business_date.isoformat(),
                "revision": case.revision,
                "decision": decision.decision if decision else "PENDING",
            } for case, decision in cases],
        }), 200
    except (ValueError, TypeError):
        return jsonify({"code": "INVALID_CORRECTION_DAY"}), 400
    except Exception:
        current_app.logger.exception("M6 correction case list unavailable.")
        return jsonify({"code": "CORRECTION_CASE_LIST_UNAVAILABLE"}), 503
