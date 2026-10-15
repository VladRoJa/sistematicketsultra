"""Exception-only paired RAW intake for Google Ads M6 late corrections.

Never called by the normal upload path. Two independently committed Warehouse
uploads may yield PARTIAL_RAW: neither staging facts nor publication is implied.
"""
from __future__ import annotations

from datetime import date
from hashlib import sha256
import os

import sqlalchemy as sa
from flask import current_app
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.extensions import db
from app.warehouse.services.google_ads_m6_manual_preview_service import (
    preview_manual_pair, GoogleAdsM6ManualPreviewError,
)
from app.warehouse.services.google_ads_m6_manual_confirm_service import (
    REPORT_TYPES, XLSX_MIME,
)
from app.warehouse.services.warehouse_document_upload_service import (
    create_warehouse_document_upload,
)
from app.warehouse.services.google_ads_m6_continuity_approval_service import CUSTOMER_ID

FLAG = "GOOGLE_ADS_M6_CORRECTION_RAW_ENABLED"
SALT = "suite-ultra-google-ads-m6-correction-raw-v1"
PURPOSE = "M6_CORRECTION_RAW_CANDIDATE_ONLY"
TTL = 900
ORIGIN = "google_ads_correction_pair"


class GoogleAdsM6CorrectionRawError(RuntimeError):
    """Fixed error code, never return XLSX data, file path or SQL."""


def _require(ok, code):
    if not ok:
        raise GoogleAdsM6CorrectionRawError(code)


def _serializer():
    _require(bool(current_app.secret_key), "SIGNING_NOT_CONFIGURED")
    return URLSafeTimedSerializer(current_app.secret_key, salt=SALT)


def _snapshot(conn, day, hashes):
    """Previous non-correction evidence is mandatory; candidates cannot bootstrap themselves."""
    previous = conn.execute(sa.text("""
        SELECT rt.key AS kind, u.id, u.file_hash_sha256, u.status,
               a.details AS upload_details, u.uploaded_by_user_id
        FROM warehouse_uploads u
        JOIN warehouse_report_types rt ON rt.id = u.report_type_id
        LEFT JOIN warehouse_audit_logs a
          ON a.upload_id = u.id AND a.action = 'UPLOAD'
        WHERE rt.key IN ('google_ads_campaign_daily',
                         'google_ads_ad_group_daily')
          AND (u.cutoff_date = :day
               OR (u.date_from <= :day AND u.date_to >= :day))
        ORDER BY u.id FOR SHARE OF u
    """), {"day": day}).mappings().all()
    original = {r["kind"] for r in previous if not (
        isinstance(r["upload_details"], dict)
        and r["upload_details"].get("upload_origin") == ORIGIN)}
    _require(set(REPORT_TYPES) <= original, "CORRECTION_PRIOR_RAW_REQUIRED")
    for kind, digest in zip(REPORT_TYPES, hashes):
        matches = [r for r in previous if r["kind"] == kind
                   and r["file_hash_sha256"] == digest]
        for row in matches:
            d = row["upload_details"]
            _require(
                row["status"] == "ACTIVE"
                and isinstance(d, dict)
                and d.get("upload_origin") == ORIGIN
                and d.get("correction_case_intent") == "CANDIDATE_ONLY",
                "CORRECTION_DUPLICATE_RAW_CONFLICT",
            )
        _require(len(matches) <= 1, "CORRECTION_DUPLICATE_RAW_CONFLICT")
    pubs = conn.execute(sa.text("""
        SELECT id, revision FROM google_ads_m6_daily_publications
        WHERE customer_id = :customer AND business_date = :day
          AND is_canonical = true
        ORDER BY id FOR SHARE
    """), {"customer": CUSTOMER_ID, "day": day}).mappings().all()
    _require(len(pubs) <= 1, "CORRECTION_CANONICAL_CONFLICT")
    p = pubs[0] if pubs else None
    return {
        "expected_publication_id": int(p["id"]) if p else None,
        "revision": int(p["revision"]) + 1 if p else 1,
    }


def preview_correction_raw_pair(*, actor_id, campaign_bytes, group_bytes, reason):
    """Authoritative read-only preview. Route verifies JWT+current Warehouse rights."""
    _require(os.getenv(FLAG, "").lower() == "true", "CORRECTION_RAW_DISABLED")
    _require(type(actor_id) is int and actor_id > 0
             and isinstance(reason, str) and 10 <= len(reason.strip()) <= 500,
             "INVALID_CORRECTION_REASON")
    try:
        preview = preview_manual_pair(
            campaign_bytes=campaign_bytes, group_bytes=group_bytes)
    except GoogleAdsM6ManualPreviewError:
        raise GoogleAdsM6CorrectionRawError("CORRECTION_PREFLIGHT_REJECTED") from None
    _require(preview["status"] == "PREFLIGHT_OK"
             and preview["customer_id"] == CUSTOMER_ID, "CORRECTION_PREFLIGHT_REJECTED")
    day = date.fromisoformat(preview["business_date"])
    hashes = (preview["campaign_sha256"], preview["ad_group_sha256"])
    with db.engine.connect() as conn:
        status = _snapshot(conn, day, hashes)
    ticket = _serializer().dumps({
        "purpose": PURPOSE, "actor": actor_id, "customer": CUSTOMER_ID,
        "day": day.isoformat(), "reason": reason.strip(),
        "campaign_sha": hashes[0], "group_sha": hashes[1],
        "expected_publication_id": status["expected_publication_id"],
        "revision": status["revision"],
    })
    return {
        **preview,
        **status,
        "correction_ticket": ticket,
        "reason": reason.strip(),
        "status": "CORRECTION_PREFLIGHT_OK",
        "eligible_for_publication": False,
        "eligible_for_structured_ingestion": False,
        "can_delete_existing_raw": False,
    }


def confirm_correction_raw_pair(*, actor_id, ticket, campaign_bytes, group_bytes,
                                upload=None):
    """Store separately audited correction-only RAW; no canonical side effects."""
    _require(os.getenv(FLAG, "").lower() == "true", "CORRECTION_RAW_DISABLED")
    _require(type(actor_id) is int and actor_id > 0
             and isinstance(ticket, str) and 0 < len(ticket) <= 4096,
             "INVALID_CORRECTION_CONFIRMATION")
    try:
        claims = _serializer().loads(ticket, max_age=TTL)
    except (BadSignature, SignatureExpired):
        raise GoogleAdsM6CorrectionRawError("INVALID_CORRECTION_CONFIRMATION") from None
    _require(
        isinstance(claims, dict)
        and claims.get("purpose") == PURPOSE
        and claims.get("actor") == actor_id
        and claims.get("customer") == CUSTOMER_ID
        and claims.get("campaign_sha") == sha256(campaign_bytes).hexdigest()
        and claims.get("group_sha") == sha256(group_bytes).hexdigest(),
        "CORRECTION_CONFIRMATION_MISMATCH",
    )
    pre = preview_correction_raw_pair(
        actor_id=actor_id, campaign_bytes=campaign_bytes,
        group_bytes=group_bytes, reason=claims.get("reason"))
    _require(
        pre["business_date"] == claims.get("day")
        and pre["expected_publication_id"] == claims.get("expected_publication_id")
        and pre["revision"] == claims.get("revision"),
        "CORRECTION_STATE_CHANGED",
    )
    day = date.fromisoformat(pre["business_date"])
    files = (campaign_bytes, group_bytes)
    hashes = (claims["campaign_sha"], claims["group_sha"])
    store = upload if upload is not None else create_warehouse_document_upload
    result = {}
    with db.engine.begin() as conn:
        conn.execute(sa.text("""
            SELECT pg_advisory_xact_lock(
                hashtext('google_ads_m6_manual_raw_pair'),
                CAST(:ordinal AS INTEGER))
        """), {"ordinal": day.toordinal()})
        # Check state while holding the day lock. The normal raw route also
        # locks this key and cannot publish by a correction upload.
        _require(_snapshot(conn, day, hashes) == {
            "expected_publication_id": claims["expected_publication_id"],
            "revision": claims["revision"],
        }, "CORRECTION_STATE_CHANGED")
        for kind, payload, digest in zip(REPORT_TYPES, files, hashes):
            # A byte-identical archive/generic upload must never be recycled
            # and mislabeled as independently authorized correction evidence.
            matches = conn.execute(sa.text("""
                SELECT u.id, u.status, u.uploaded_by_user_id,
                       a.performed_by_user_id, a.details
                FROM warehouse_uploads u
                JOIN warehouse_report_types rt ON rt.id = u.report_type_id
                LEFT JOIN warehouse_audit_logs a
                  ON a.upload_id = u.id AND a.action = 'UPLOAD'
                WHERE rt.key = :kind AND u.file_hash_sha256 = :digest
                ORDER BY u.id FOR SHARE OF u
            """), {"kind": kind, "digest": digest}).mappings().all()
            if matches:
                _require(
                    len(matches) == 1 and matches[0]["status"] == "ACTIVE"
                    and matches[0]["uploaded_by_user_id"] == actor_id
                    and matches[0]["performed_by_user_id"] == actor_id
                    and isinstance(matches[0]["details"], dict)
                    and matches[0]["details"].get("upload_origin") == ORIGIN
                    and matches[0]["details"].get("manual_pair_business_date") ==
                        day.isoformat()
                    and matches[0]["details"].get("manual_pair_campaign_sha256") == hashes[0]
                    and matches[0]["details"].get("manual_pair_group_sha256") == hashes[1],
                    "CORRECTION_DUPLICATE_RAW_CONFLICT",
                )
            try:
                saved = store(
                    report_type_key=kind,
                    original_filename=f"{kind}_correction_{day.isoformat()}.xlsx",
                    content_type=XLSX_MIME, file_bytes=payload,
                    uploaded_by_user_id=actor_id,
                    cutoff_date=day, date_from=day, date_to=day,
                    audit_details={
                        "upload_origin": ORIGIN,
                        "correction_case_intent": "CANDIDATE_ONLY",
                        "manual_pair_business_date": day.isoformat(),
                        "manual_pair_campaign_sha256": hashes[0],
                        "manual_pair_group_sha256": hashes[1],
                        "expected_publication_id": claims["expected_publication_id"],
                        "intended_revision": claims["revision"],
                        "reason_sha256": sha256(claims["reason"].encode("utf-8")).hexdigest(),
                        "publication": "NOT_AUTHORIZED",
                    },
                )
                _require(
                    type(saved.get("upload_id")) is int
                    and saved.get("file_hash_sha256") == digest
                    and saved.get("report_type_key") == kind
                    and saved.get("date_from") == day.isoformat()
                    and saved.get("date_to") == day.isoformat()
                    and saved.get("upload_status") in ("created", "reused_existing"),
                    "CORRECTION_WAREHOUSE_RESPONSE_INVALID",
                )
                if matches:
                    _require(saved["upload_id"] == matches[0]["id"]
                             and saved["upload_status"] == "reused_existing",
                             "CORRECTION_DUPLICATE_RAW_CONFLICT")
                else:
                    _require(saved["upload_status"] == "created",
                             "CORRECTION_DUPLICATE_RAW_CONFLICT")
            except Exception:
                # Warehouse commits each physical file independently. Never
                # pretend partial success is an atomic or publishable pair.
                return {
                    "status": "PARTIAL_RAW" if result else "RAW_STAGE_FAILED",
                    "business_date": day.isoformat(),
                    "uploads": result,
                    "eligible_for_publication": False,
                    "eligible_for_structured_ingestion": False,
                }
            result[kind] = {
                "upload_id": saved["upload_id"],
                "file_hash_sha256": digest,
                "reused_existing": saved["upload_status"] == "reused_existing",
            }
    return {
        "status": "CORRECTION_RAW_PAIR_STAGED",
        "business_date": day.isoformat(),
        "revision": claims["revision"],
        "expected_publication_id": claims["expected_publication_id"],
        "uploads": result,
        "eligible_for_publication": False,
        "eligible_for_structured_ingestion": False,
        "funnel_publication": "NOT_AUTHORIZED",
    }
