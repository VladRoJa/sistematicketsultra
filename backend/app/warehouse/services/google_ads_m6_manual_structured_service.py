"""Atomic M6 structured staging from two explicitly confirmed Warehouse RAW.

No generic dispatcher, late correction, identity approval or Funnel publishing.
Both metric tables and both audit rows share ONE PostgreSQL transaction.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
from zoneinfo import ZoneInfo
import sqlalchemy as sa

from app.extensions import db
from app.models.google_ads_daily import GoogleAdsDailyMetricORM
from app.models.google_ads_ad_group_daily import GoogleAdsAdGroupDailyMetricORM
from app.models.warehouse import WarehouseAuditLogORM
from app.warehouse.services.google_ads_daily_ingestion_service import (
    _customer_id, _upload_content, GoogleAdsDailyIngestionError,
)
from app.warehouse.services.google_ads_daily_xlsx_parser import (
    GoogleAdsXlsxValidationError, parse_google_ads_daily_xlsx,
)
from app.warehouse.services.google_ads_ad_group_daily_xlsx_parser import (
    parse_google_ads_ad_group_daily_xlsx,
)
from app.warehouse.services.google_ads_m6_daily_pair_preflight import (
    preflight_daily_pair, GoogleAdsM6DailyPairError,
)
from app.warehouse.services.google_ads_m6_manual_preview_service import _historical_catalog
from app.warehouse.services.google_ads_m6_continuity_approval_service import (
    CUSTOMER_ID, START, M5_REFERENCE, M6_REFERENCE,
    CAMPAIGN_UPLOAD_ID, GROUP_UPLOAD_ID,
)

CONFIRMATION = "INGESTAR_GOOGLE_ADS_M6_SIN_PUBLICAR"
AUDIT_ACTION = "GOOGLE_ADS_M6_PAIR_IMPORT"
CAMPAIGN_TYPE = "google_ads_campaign_daily"
GROUP_TYPE = "google_ads_ad_group_daily"


class GoogleAdsM6ManualStructuredError(RuntimeError):
    """Safe, fixed response codes."""


def require(ok: bool, code: str) -> None:
    if not ok:
        raise GoogleAdsM6ManualStructuredError(code)


def _load_pair(campaign_id: int, group_id: int):
    try:
        camp, camp_bytes = _upload_content(
            campaign_id, report_type_key=CAMPAIGN_TYPE)
        grp, grp_bytes = _upload_content(
            group_id, report_type_key=GROUP_TYPE)
        # Capture metadata before closing ORM session (detached objects).
        metadata = [
            {
                "id": u.id, "status": u.status,
                "cutoff_date": u.cutoff_date,
                "date_from": u.date_from, "date_to": u.date_to,
                "source_file_deleted_at": u.source_file_deleted_at,
                "file_hash_sha256": u.file_hash_sha256,
                "file_size_bytes": u.file_size_bytes,
            }
            for u in (camp, grp)
        ]
        campaign = parse_google_ads_daily_xlsx(camp_bytes)
        group = parse_google_ads_ad_group_daily_xlsx(grp_bytes)
    except (GoogleAdsDailyIngestionError, GoogleAdsXlsxValidationError):
        raise GoogleAdsM6ManualStructuredError("RAW_PAIR_UNREADABLE") from None
    finally:
        db.session.remove()

    today = datetime.now(ZoneInfo("America/Tijuana")).date()
    day = campaign.date_from
    require(
        campaign.date_from == campaign.date_to == group.date_from == group.date_to
        and date(2026, 10, 13) <= day < today, "RAW_PAIR_INVALID_PERIOD")
    hashes = (sha256(camp_bytes).hexdigest(), sha256(grp_bytes).hexdigest())
    for m, raw, digest in zip(metadata, (camp_bytes, grp_bytes), hashes):
        require(
            m["status"] == "ACTIVE"
            and m["cutoff_date"] == m["date_from"] == m["date_to"] == day
            and m["source_file_deleted_at"] is None
            and m["file_size_bytes"] == len(raw)
            and m["file_hash_sha256"] == digest, "RAW_PAIR_METADATA_MISMATCH",
        )
    try:
        keys, pairs, mapping = _historical_catalog()
    finally:
        db.session.remove()
    try:
        summary = preflight_daily_pair(
            business_date=day, today_local=today,
            campaign_report=campaign, group_report=group,
            historical_campaign_keys=keys,
            historical_group_pairs=pairs,
            approved_branch_by_pair=mapping,
        )
    except GoogleAdsM6DailyPairError:
        raise GoogleAdsM6ManualStructuredError("RAW_PAIR_PREFLIGHT_REJECTED") from None
    require(summary.get("status") == "PREFLIGHT_OK", "RAW_PAIR_PREFLIGHT_REJECTED")
    return campaign, group, summary, mapping, hashes


def _approval(conn, day: date, mapping: dict) -> int:
    rows = conn.execute(sa.text("""
        SELECT id, approval_reference, source_approval_reference, valid_from,
               valid_to, source_campaign_upload_id, source_ad_group_upload_id,
               approved_by_user_id, approved_on
        FROM google_ads_branch_approval_versions WHERE customer_id = :customer
    """), {"customer": CUSTOMER_ID}).mappings().all()
    require(len(rows) == 1, "M6_APPROVAL_REQUIRED")
    row = rows[0]
    require(
        row["approval_reference"] == M6_REFERENCE
        and row["source_approval_reference"] == M5_REFERENCE
        and row["valid_from"] == START
        and row["valid_to"] is None
        and row["source_campaign_upload_id"] == CAMPAIGN_UPLOAD_ID
        and row["source_ad_group_upload_id"] == GROUP_UPLOAD_ID
        and row["approved_by_user_id"] is not None
        and row["approved_on"] >= date(2026, 10, 13)
        and day >= row["valid_from"], "M6_APPROVAL_REQUIRED")
    identities = conn.execute(sa.text("""
        SELECT campaign_key, ad_group_key, sucursal_canon
        FROM google_ads_branch_approved_identities
        WHERE approval_version_id = :version
    """), {"version": row["id"]}).mappings().all()
    actual = {(r["campaign_key"], r["ad_group_key"]): r["sucursal_canon"]
              for r in identities}
    require(
        len(identities) == len(actual) == 26
        and len(set(actual.values())) == 26
        and actual == mapping, "M6_APPROVED_IDENTITIES_MISMATCH")
    return int(row["id"])


def _provenance(conn, upload_id: int, actor: int, day: date,
                campaign_sha: str, group_sha: str, report_type: str) -> None:
    uploads = conn.execute(sa.text("""
        SELECT u.id, u.status, u.uploaded_by_user_id, u.file_hash_sha256,
               u.cutoff_date, u.date_from, u.date_to, u.source_file_deleted_at,
               rt.key AS report_type_key
        FROM warehouse_uploads u
        JOIN warehouse_report_types rt ON rt.id = u.report_type_id
        WHERE u.id = :id FOR SHARE OF u
    """), {"id": upload_id}).mappings().all()
    require(len(uploads) == 1, "RAW_PAIR_PROVENANCE_INVALID")
    u = uploads[0]
    expected = campaign_sha if report_type == CAMPAIGN_TYPE else group_sha
    require(
        u["status"] == "ACTIVE"
        and u["uploaded_by_user_id"] == actor
        and u["file_hash_sha256"] == expected
        and u["cutoff_date"] == u["date_from"] == u["date_to"] == day
        and u["source_file_deleted_at"] is None
        and u["report_type_key"] == report_type,
        "RAW_PAIR_PROVENANCE_INVALID",
    )
    audits = conn.execute(sa.text("""
        SELECT performed_by_user_id, details FROM warehouse_audit_logs
        WHERE upload_id = :id AND action = 'UPLOAD'
    """), {"id": upload_id}).mappings().all()
    require(len(audits) == 1, "RAW_PAIR_PROVENANCE_INVALID")
    details = audits[0]["details"]
    require(
        audits[0]["performed_by_user_id"] == actor
        and isinstance(details, dict)
        and details.get("upload_origin") == "google_ads_manual_pair"
        and details.get("manual_pair_business_date") == day.isoformat()
        and details.get("manual_pair_campaign_sha256") == campaign_sha
        and details.get("manual_pair_group_sha256") == group_sha
        and details.get("publication") == "NOT_AUTHORIZED",
        "RAW_PAIR_PROVENANCE_INVALID",
    )


def _campaign_record(row, upload_id: int) -> dict:
    return {
        "customer_id": CUSTOMER_ID, "campaign_id": None,
        "campaign_key": row.campaign_key, "campaign_name": row.campaign_name,
        "report_date": row.report_date, "currency_code": row.currency_code,
        "cost": row.cost, "clicks": row.clicks,
        "impressions": row.impressions, "conversions": row.conversions,
        "conversion_value": row.conversion_value,
        "source_kind": "WAREHOUSE_XLSX", "source_upload_id": upload_id,
    }


def _group_record(row, upload_id: int) -> dict:
    return {
        **_campaign_record(row, upload_id),
        "ad_group_id": None, "ad_group_key": row.ad_group_key,
        "ad_group_name": row.ad_group_name,
        "free_pass_conversions": row.free_pass_conversions,
        "web_purchase_conversions": row.web_purchase_conversions,
    }


def _existing_matches(old: list[dict], wanted: list[dict],
                      keys: tuple[str, ...]) -> bool:
    if not old:
        return False
    require(len(old) == len(wanted), "EXISTING_STRUCTURED_FACT_CONFLICT")
    old_index = {tuple(r[k] for k in keys): r for r in old}
    require(len(old_index) == len(old), "EXISTING_STRUCTURED_FACT_CONFLICT")
    for row in wanted:
        previous = old_index.get(tuple(row[k] for k in keys))
        require(previous is not None, "EXISTING_STRUCTURED_FACT_CONFLICT")
        require(all(previous[field] == value for field, value in row.items()),
                "EXISTING_STRUCTURED_FACT_CONFLICT")
    return True


def stage_structured_manual_pair(*, actor_id: int, campaign_upload_id: int,
                                 group_upload_id: int) -> dict:
    """Stage both tables with one atomic commit; no publication side effects."""
    require(
        type(actor_id) is int and actor_id > 0
        and type(campaign_upload_id) is int and campaign_upload_id > 0
        and type(group_upload_id) is int and group_upload_id > 0
        and campaign_upload_id != group_upload_id,
        "INVALID_STRUCTURED_REQUEST",
    )
    try:
        customer = _customer_id()
    except GoogleAdsDailyIngestionError:
        raise GoogleAdsM6ManualStructuredError("GOOGLE_ADS_CUSTOMER_NOT_READY") from None
    require(customer == CUSTOMER_ID, "GOOGLE_ADS_CUSTOMER_NOT_READY")
    campaign, group, summary, mapping, digests = _load_pair(
        campaign_upload_id, group_upload_id)
    day = campaign.date_from
    campaign_rows = [_campaign_record(r, campaign_upload_id) for r in campaign.rows]
    group_rows = [_group_record(r, group_upload_id) for r in group.rows]
    require(len(campaign_rows) == 27 and len(group_rows) == 43,
            "RAW_PAIR_PREFLIGHT_REJECTED")

    with db.engine.begin() as conn:
        conn.execute(sa.text("""
            SELECT pg_advisory_xact_lock(
              hashtext('google_ads_m6_manual_structured_pair'),
              CAST(:ordinal AS INTEGER))
        """), {"ordinal": day.toordinal()})
        principal = conn.execute(sa.text("""
            SELECT username, rol FROM users WHERE id = :id FOR UPDATE
        """), {"id": actor_id}).mappings().one_or_none()
        require(
            principal is not None
            and str(principal["username"]).strip().casefold() == "admicorp"
            and str(principal["rol"]).strip().upper() == "ADMINISTRADOR",
            "FORBIDDEN",
        )
        version = _approval(conn, day, mapping)
        for upload_id, kind in (
            (campaign_upload_id, CAMPAIGN_TYPE),
            (group_upload_id, GROUP_TYPE),
        ):
            _provenance(
                conn, upload_id, actor_id, day, digests[0], digests[1], kind,
            )
        old_campaign = [
            dict(r) for r in conn.execute(sa.text("""
                SELECT * FROM google_ads_daily_metrics
                WHERE customer_id = :customer AND report_date = :day
            """), {"customer": CUSTOMER_ID, "day": day}).mappings()
        ]
        old_groups = [
            dict(r) for r in conn.execute(sa.text("""
                SELECT * FROM google_ads_ad_group_daily_metrics
                WHERE customer_id = :customer AND report_date = :day
            """), {"customer": CUSTOMER_ID, "day": day}).mappings()
        ]
        same_c = _existing_matches(old_campaign, campaign_rows, ("campaign_key",))
        same_g = _existing_matches(
            old_groups, group_rows, ("campaign_key", "ad_group_key"))
        require(same_c == same_g, "EXISTING_STRUCTURED_FACT_CONFLICT")
        status = "ALREADY_INGESTED" if same_c else "STRUCTURED_PAIR_STAGED"
        if not same_c:
            conn.execute(GoogleAdsDailyMetricORM.__table__.insert(), campaign_rows)
            conn.execute(GoogleAdsAdGroupDailyMetricORM.__table__.insert(), group_rows)
            for upload_id, kind, count in (
                (campaign_upload_id, CAMPAIGN_TYPE, len(campaign_rows)),
                (group_upload_id, GROUP_TYPE, len(group_rows)),
            ):
                conn.execute(WarehouseAuditLogORM.__table__.insert().values(
                    upload_id=upload_id, action=AUDIT_ACTION,
                    performed_by_user_id=actor_id,
                    details={
                        "customer_id": CUSTOMER_ID,
                        "business_date": day.isoformat(),
                        "approval_version_id": version,
                        "campaign_upload_id": campaign_upload_id,
                        "ad_group_upload_id": group_upload_id,
                        "report_type_key": kind,
                        "rows_created": count,
                        "publication": "NOT_AUTHORIZED",
                    },
                ))
    return {
        "status": status,
        "business_date": day.isoformat(),
        "campaign_upload_id": campaign_upload_id,
        "ad_group_upload_id": group_upload_id,
        "campaign_rows": len(campaign_rows),
        "group_rows": len(group_rows),
        "account_cost_mxn": summary["account_cost_mxn"],
        "branch_cost_mxn": summary["branch_cost_mxn"],
        "unassigned_cost_mxn": summary["unassigned_cost_mxn"],
        "approval_version_id": version,
        "eligible_for_publication": False,
        "funnel_publication": "NOT_AUTHORIZED",
    }
