"""Manual M6 RAW confirmation: signed preview and revalidation, never publish.

Warehouse's document service commits every individual upload. The guarded
logical pair therefore has explicit PARTIAL_RAW status if a second file fails;
do not represent it as a single atomic transaction.
"""
from __future__ import annotations

from datetime import date
from hashlib import sha256
import os
import re

import sqlalchemy as sa
from flask import current_app
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.extensions import db
from app.models.warehouse import WarehouseAuditLogORM
from app.warehouse.services.google_ads_m6_manual_preview_service import (
    GoogleAdsM6ManualPreviewError, preview_manual_pair,
)
from app.warehouse.services.warehouse_document_upload_service import (
    create_warehouse_document_upload,
)

SALT = "suite-ultra-google-ads-m6-manual-raw-confirm-v1"
PURPOSE = "M6_MANUAL_RAW_STAGE"
TICKET_TTL_SECONDS = 900
REPORT_TYPES = ("google_ads_campaign_daily", "google_ads_ad_group_daily")
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class GoogleAdsM6ManualConfirmError(RuntimeError):
    """Static codes only: no XLSX bytes, SQL, filesystem or signed secrets."""


def _serializer():
    # Never fall back to hardcoded application secrets.
    key = current_app.secret_key
    if not key:
        raise GoogleAdsM6ManualConfirmError("SERVER_SIGNING_KEY_MISSING")
    return URLSafeTimedSerializer(key, salt=SALT)


def issue_raw_confirmation_ticket(preview: dict, *, actor_id: int) -> str:
    """Only call after a successful server-side XLSX pair preview."""
    if (preview.get("status") != "PREFLIGHT_OK"
            or type(actor_id) is not int or actor_id <= 0):
        raise GoogleAdsM6ManualConfirmError("PREVIEW_NOT_ELIGIBLE")
    for digest in ("campaign_sha256", "ad_group_sha256"):
        if not re.fullmatch("[a-f0-9]{64}", str(preview.get(digest, ""))):
            raise GoogleAdsM6ManualConfirmError("INVALID_PREVIEW_DIGEST")
    return _serializer().dumps({
        "purpose": PURPOSE,
        "actor_id": actor_id,
        "business_date": preview["business_date"],
        "customer_id": preview["customer_id"],
        "campaign_sha256": preview["campaign_sha256"],
        "ad_group_sha256": preview["ad_group_sha256"],
    })


def _verify_ticket(ticket: str, *, actor_id: int,
                   campaign_bytes: bytes, group_bytes: bytes) -> dict:
    if not isinstance(ticket, str) or not 0 < len(ticket) <= 4096:
        raise GoogleAdsM6ManualConfirmError("INVALID_CONFIRMATION_TICKET")
    try:
        claims = _serializer().loads(ticket, max_age=TICKET_TTL_SECONDS)
    except (BadSignature, SignatureExpired):
        raise GoogleAdsM6ManualConfirmError("INVALID_OR_EXPIRED_CONFIRMATION") from None
    if (not isinstance(claims, dict)
            or claims.get("purpose") != PURPOSE
            or type(claims.get("actor_id")) is not int
            or claims["actor_id"] != actor_id
            or claims.get("campaign_sha256") != sha256(campaign_bytes).hexdigest()
            or claims.get("ad_group_sha256") != sha256(group_bytes).hexdigest()):
        raise GoogleAdsM6ManualConfirmError("CONFIRMATION_MISMATCH")
    return claims


def _existing_raw_documents(conn, day: date) -> list[dict]:
    """Include archived/overlapping reports: revisions need explicit review."""
    rows = conn.execute(sa.text("""
        SELECT rt.key AS report_type_key, u.id, u.file_hash_sha256,
               u.status, u.date_from, u.date_to
        FROM warehouse_uploads AS u
        JOIN warehouse_report_types AS rt ON rt.id = u.report_type_id
        WHERE rt.key IN ('google_ads_campaign_daily',
                         'google_ads_ad_group_daily')
          AND (u.cutoff_date = :day
               OR (u.date_from <= :day AND u.date_to >= :day))
        ORDER BY u.id
    """), {"day": day}).mappings().all()
    return [dict(row) for row in rows]



RECOVERY_ENV = "GOOGLE_ADS_M6_LEGACY_RECOVERY_UPLOAD_IDS"
RECOVERY_AUDIT = "GOOGLE_ADS_M6_RAW_SUPERSEDED"


def _legacy_recovery_context(conn, *, day: date, actor_id: int,
                             existing: list[dict], hashes: dict) -> dict | None:
    """A deliberately narrow, opt-in recovery of TWO misclassified RAWs.

    The configuration lists the immutable Warehouse IDs explicitly.  Never
    accept arbitrary archive status, changed metrics, or an already published
    day as grounds for overwriting its evidence.
    """
    configured = os.getenv(RECOVERY_ENV, "")
    if not re.fullmatch(r"[1-9][0-9]*,[1-9][0-9]*", configured):
        return None
    ids = sorted(int(v) for v in configured.split(","))
    if ids[0] == ids[1]:
        return None

    # Allow correctly staged new files as well, so a partial RAW stage can
    # safely resume and a completed stage is idempotent while configured.
    conflicting = [
        row for row in existing
        if (row.get("report_type_key") not in hashes
            or row.get("file_hash_sha256") != hashes.get(row.get("report_type_key"))
            or row.get("date_from") != day or row.get("date_to") != day)
    ]
    if (len(conflicting) != 2
            or sorted(row.get("id") for row in conflicting) != ids
            or {row.get("report_type_key") for row in conflicting} != set(REPORT_TYPES)
            or len({row.get("file_hash_sha256") for row in conflicting}) != 1
            or not conflicting[0].get("file_hash_sha256")
            or any(row.get("date_from") != day or row.get("date_to") != day
                   for row in conflicting)):
        return None
    old_hash = conflicting[0]["file_hash_sha256"]
    # An ordinary same-hash reupload is not evidence of the known error:
    # the two legacy report types must share ONE wrong group-report file.
    if old_hash in hashes.values():
        return None

    evidence = conn.execute(sa.text("""
        SELECT u.id, rt.key AS kind, u.status, u.cutoff_date,
               u.uploaded_by_user_id, u.source_file_deleted_at,
               a.performed_by_user_id AS audited_by,
               a.details->>'upload_origin' AS origin
        FROM warehouse_uploads u
        JOIN warehouse_report_types rt ON rt.id = u.report_type_id
        JOIN warehouse_audit_logs a
          ON a.upload_id = u.id AND a.action = 'UPLOAD'
        WHERE u.id IN (:first, :second)
        ORDER BY u.id
    """), {"first": ids[0], "second": ids[1]}).mappings().all()
    if (len(evidence) != 2
            or [row["id"] for row in evidence] != ids
            or {row["kind"] for row in evidence} != set(REPORT_TYPES)
            or any(row["status"] != "ACTIVE"
                   or row["cutoff_date"] is not None
                   or row["source_file_deleted_at"] is not None
                   or row["uploaded_by_user_id"] != actor_id
                   or row["audited_by"] != actor_id
                   or row["origin"] != "manual_route"
                   for row in evidence)):
        return None

    # Neither structured source table nor publication history may have a
    # record for this date (regardless of customer or upload source).
    counts = conn.execute(sa.text("""
        SELECT
          (SELECT COUNT(*) FROM google_ads_daily_metrics
           WHERE report_date = :day) AS campaigns,
          (SELECT COUNT(*) FROM google_ads_ad_group_daily_metrics
           WHERE report_date = :day) AS groups,
          (SELECT COUNT(*) FROM google_ads_m6_daily_publications
           WHERE business_date = :day) AS publications
    """), {"day": day}).mappings().one()
    if any(counts[k] for k in ("campaigns", "groups", "publications")):
        return None
    return {"prior_ids": ids, "prior_sha256": old_hash}


def _audit_legacy_recovery(conn, *, actor_id: int, day: date,
                           recovery: dict, outputs: dict, hashes: dict) -> None:
    """Only after both new RAWs succeeded; preserve original rows/files."""
    old_ids = recovery["prior_ids"]
    details = {
        "business_date": day.isoformat(),
        "reason": "MISCLASSIFIED_DUPLICATE_GROUP_REPORT",
        "prior_upload_ids": old_ids,
        "prior_sha256": recovery["prior_sha256"],
        "new_campaign_upload_id": outputs[REPORT_TYPES[0]]["upload_id"],
        "new_group_upload_id": outputs[REPORT_TYPES[1]]["upload_id"],
        "new_campaign_sha256": hashes[REPORT_TYPES[0]],
        "new_group_sha256": hashes[REPORT_TYPES[1]],
        "publication": "NOT_AUTHORIZED",
    }
    prior = conn.execute(sa.text("""
        SELECT upload_id, performed_by_user_id, details
        FROM warehouse_audit_logs
        WHERE action = :action AND upload_id IN (:first, :second)
    """), {"action": RECOVERY_AUDIT,
           "first": old_ids[0], "second": old_ids[1]}).mappings().all()
    if prior:
        if (len(prior) != 2
                or {row["upload_id"] for row in prior} != set(old_ids)
                or any(row["performed_by_user_id"] != actor_id
                       or row["details"] != details for row in prior)):
            raise GoogleAdsM6ManualConfirmError("LEGACY_RECOVERY_AUDIT_CONFLICT")
        return
    for old_id in old_ids:
        conn.execute(WarehouseAuditLogORM.__table__.insert().values(
            upload_id=old_id, action=RECOVERY_AUDIT,
            performed_by_user_id=actor_id, details=details,
        ))


def confirm_google_ads_m6_manual_pair(
    *, actor_id: int, ticket: str,
    campaign_bytes: bytes, group_bytes: bytes,
    upload=None, existing_lookup=None,
) -> dict:
    """Stage RAW only after signed ticket, reparse, and pair reconciliation.

    The caller must have verified the JWT principal against DB and the
    Warehouse can_upload permission before this function is invoked.
    """
    claims = _verify_ticket(
        ticket, actor_id=actor_id,
        campaign_bytes=campaign_bytes, group_bytes=group_bytes,
    )
    try:
        preview = preview_manual_pair(
            campaign_bytes=campaign_bytes, group_bytes=group_bytes,
        )
    except GoogleAdsM6ManualPreviewError:
        raise GoogleAdsM6ManualConfirmError("REVALIDATION_REJECTED") from None
    if (preview["business_date"] != claims.get("business_date")
            or preview["customer_id"] != claims.get("customer_id")
            or preview["status"] != "PREFLIGHT_OK"):
        raise GoogleAdsM6ManualConfirmError("CONFIRMATION_MISMATCH")
    day = date.fromisoformat(preview["business_date"])
    hashes = {
        REPORT_TYPES[0]: preview["campaign_sha256"],
        REPORT_TYPES[1]: preview["ad_group_sha256"],
    }
    files = {
        REPORT_TYPES[0]: campaign_bytes,
        REPORT_TYPES[1]: group_bytes,
    }

    store = create_warehouse_document_upload if upload is None else upload
    outputs = {}
    # Advisory lock serializes only callers using this M6 manual flow.
    # Warehouse's own uploader commits in a separate session.
    with db.engine.begin() as conn:
        conn.execute(sa.text("""
            SELECT pg_advisory_xact_lock(
                hashtext('google_ads_m6_manual_raw_pair'),
                CAST(:day_ordinal AS INTEGER))
        """), {"day_ordinal": day.toordinal()})
        existing = (_existing_raw_documents(conn, day) if existing_lookup is None
                    else existing_lookup(day))
        conflicting = [
            row for row in existing
            if (hashes.get(row.get("report_type_key"))
                != row.get("file_hash_sha256")
                or row.get("date_from") != day or row.get("date_to") != day)
        ]
        recovery = None
        if conflicting:
            recovery = _legacy_recovery_context(
                conn, day=day, actor_id=actor_id,
                existing=existing, hashes=hashes,
            )
            if recovery is None:
                raise GoogleAdsM6ManualConfirmError("EXISTING_PERIOD_CONFLICT")
        for kind in REPORT_TYPES:
            try:
                saved = store(
                    report_type_key=kind,
                    original_filename=f"{kind}_{day.isoformat()}.xlsx",
                    content_type=XLSX_MIME,
                    file_bytes=files[kind],
                    uploaded_by_user_id=actor_id,
                    cutoff_date=day, date_from=day, date_to=day,
                    audit_details={
                        "upload_origin": "google_ads_manual_pair",
                        "manual_pair_business_date": day.isoformat(),
                        "manual_pair_campaign_sha256": hashes[REPORT_TYPES[0]],
                        "manual_pair_group_sha256": hashes[REPORT_TYPES[1]],
                        "publication": "NOT_AUTHORIZED",
                        **({
                            "legacy_recovery_prior_upload_ids": recovery["prior_ids"],
                            "legacy_recovery_prior_sha256": recovery["prior_sha256"],
                        } if recovery else {}),
                    },
                )
                if (not isinstance(saved, dict)
                        or type(saved.get("upload_id")) is not int
                        or saved["upload_id"] <= 0
                        or saved.get("file_hash_sha256") != hashes[kind]
                        or saved.get("report_type_key") != kind
                        or saved.get("date_from") != day.isoformat()
                        or saved.get("date_to") != day.isoformat()
                        or saved.get("upload_status") not in (
                            "created", "reused_existing",
                        )):
                    raise GoogleAdsM6ManualConfirmError("WAREHOUSE_RESPONSE_INVALID")
            except Exception:
                # First RAW upload may already be committed: never publish.
                return {
                    "status": "PARTIAL_RAW" if outputs else "RAW_STAGE_FAILED",
                    "business_date": day.isoformat(),
                    "uploads": outputs,
                    "code": "RAW_STAGE_INCOMPLETE_RETRY_OR_REVIEW",
                    "eligible_for_structured_ingestion": False,
                    "eligible_for_publication": False,
                }
            outputs[kind] = {
                "upload_id": saved["upload_id"],
                "file_hash_sha256": saved["file_hash_sha256"],
                "reused_existing": saved["upload_status"] == "reused_existing",
            }
        if recovery is not None:
            _audit_legacy_recovery(
                conn, actor_id=actor_id, day=day, recovery=recovery,
                outputs=outputs, hashes=hashes,
            )

    return {
        "status": "RAW_PAIR_STAGED",
        "business_date": day.isoformat(),
        "uploads": outputs,
        "account_cost_mxn": preview["account_cost_mxn"],
        "branch_cost_mxn": preview["branch_cost_mxn"],
        "unassigned_cost_mxn": preview["unassigned_cost_mxn"],
        "initial_m6_approval_verified": False,
        "eligible_for_structured_ingestion": False,
        "eligible_for_publication": False,
    }
