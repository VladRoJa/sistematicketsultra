"""Read-only Google Ads M6 day correction inventory.

Never authorize replacements based on status. Warehouse RAW is append-only
evidence, and canonical M6 cannot be silently overwritten. Current revision
and metric schemas do not yet support versioned corrected daily facts.
"""
from __future__ import annotations

from datetime import date

import sqlalchemy as sa

from app.extensions import db
from app.warehouse.services.google_ads_m6_continuity_approval_service import CUSTOMER_ID


def inspect_m6_day_for_correction(*, business_date: date) -> dict:
    """Provide safe state evidence only. PG transaction is explicitly READ ONLY."""
    if not isinstance(business_date, date) or business_date < date(2026, 10, 13):
        raise ValueError("INVALID_CORRECTION_DAY")
    with db.engine.connect() as conn:
        with conn.begin():
            conn.execute(sa.text("SET TRANSACTION READ ONLY"))
            uploads = conn.execute(sa.text("""
                SELECT u.id, rt.key AS kind, u.status, u.date_from, u.date_to,
                       u.file_hash_sha256, u.source_file_deleted_at,
                       (SELECT COUNT(*) FROM warehouse_audit_logs a
                        WHERE a.upload_id = u.id AND a.action = 'UPLOAD'
                          AND a.details->>'upload_origin' = 'google_ads_manual_pair'
                       ) AS manual_pair_upload_audits,
                       (SELECT COUNT(*) FROM warehouse_audit_logs a
                        WHERE a.upload_id = u.id
                          AND a.action = 'GOOGLE_ADS_M6_PAIR_IMPORT'
                       ) AS pair_import_audits,
                       (SELECT COUNT(*) FROM warehouse_audit_logs a
                        WHERE a.upload_id = u.id
                          AND a.action = 'GOOGLE_ADS_M6_PAIR_PUBLISH'
                       ) AS pair_publish_audits
                FROM warehouse_uploads u
                JOIN warehouse_report_types rt ON rt.id = u.report_type_id
                WHERE rt.key IN ('google_ads_campaign_daily',
                                 'google_ads_ad_group_daily')
                  AND (u.cutoff_date = :day OR
                       (u.date_from <= :day AND u.date_to >= :day))
                ORDER BY u.id
            """), {"day": business_date}).mappings().all()
            campaign = conn.execute(sa.text("""
                SELECT source_upload_id, COUNT(*) AS rows
                FROM google_ads_daily_metrics
                WHERE customer_id = :customer AND report_date = :day
                GROUP BY source_upload_id ORDER BY source_upload_id
            """), {"customer": CUSTOMER_ID, "day": business_date}).mappings().all()
            groups = conn.execute(sa.text("""
                SELECT source_upload_id, COUNT(*) AS rows
                FROM google_ads_ad_group_daily_metrics
                WHERE customer_id = :customer AND report_date = :day
                GROUP BY source_upload_id ORDER BY source_upload_id
            """), {"customer": CUSTOMER_ID, "day": business_date}).mappings().all()
            publications = conn.execute(sa.text("""
                SELECT id, revision, is_canonical, campaign_upload_id,
                       ad_group_upload_id, approval_version_id
                FROM google_ads_m6_daily_publications
                WHERE customer_id = :customer AND business_date = :day
                ORDER BY revision, id
            """), {"customer": CUSTOMER_ID, "day": business_date}).mappings().all()

    raw = [
        {
            "upload_id": int(row["id"]),
            "report_type_key": str(row["kind"]),
            "status": row["status"],
            "period_from": row["date_from"].isoformat() if row["date_from"] else None,
            "period_to": row["date_to"].isoformat() if row["date_to"] else None,
            "sha256_prefix": str(row["file_hash_sha256"])[:12],
            "source_deleted": row["source_file_deleted_at"] is not None,
            "manual_pair_upload_audit_count": int(row["manual_pair_upload_audits"]),
            "pair_import_audit_count": int(row["pair_import_audits"]),
            "pair_publish_audit_count": int(row["pair_publish_audits"]),
        }
        for row in uploads
    ]
    campaign_sources = [
        {"upload_id": int(row["source_upload_id"]), "rows": int(row["rows"])}
        for row in campaign if row["source_upload_id"] is not None
    ]
    group_sources = [
        {"upload_id": int(row["source_upload_id"]), "rows": int(row["rows"])}
        for row in groups if row["source_upload_id"] is not None
    ]
    campaign_total = sum(int(row["rows"]) for row in campaign)
    group_total = sum(int(row["rows"]) for row in groups)
    published = [
        {
            "publication_id": int(row["id"]), "revision": int(row["revision"]),
            "is_canonical": bool(row["is_canonical"]),
            "campaign_upload_id": int(row["campaign_upload_id"]),
            "ad_group_upload_id": int(row["ad_group_upload_id"]),
            "approval_version_id": int(row["approval_version_id"]),
        }
        for row in publications
    ]
    if any(x["is_canonical"] for x in published):
        state = "CANONICAL_PUBLISHED"
    elif published:
        state = "PUBLICATION_REVIEW_REQUIRED"
    elif campaign_total or group_total:
        if campaign_total == 27 and group_total == 43:
            state = "STRUCTURED_UNPUBLISHED"
        else:
            state = "STRUCTURED_INCONSISTENT"
    elif raw:
        state = "RAW_ONLY_UNPUBLISHED"
    else:
        state = "NO_RECORDS"

    # Archiving never removes a collision. This endpoint cannot approve
    # replacements or treat archival status as permission to reload the day.
    return {
        "business_date": business_date.isoformat(),
        "customer_id": CUSTOMER_ID,
        "state": state,
        "raw_reports": raw,
        "structured": {
            "campaign_rows": campaign_total, "group_rows": group_total,
            "campaign_sources": campaign_sources, "group_sources": group_sources,
        },
        "publications": published,
        "has_existing_period_evidence": bool(raw or campaign_total or group_total or published),
        "replacement_authorized": False,
        "can_delete_existing_raw": False,
        "can_auto_republish": False,
        "next_action": (
            "REVIEW_CORRECTION_POLICY_REQUIRED"
            if raw or campaign_total or group_total or published
            else "NORMAL_M6_PAIR_PREFLIGHT"
        ),
    }
