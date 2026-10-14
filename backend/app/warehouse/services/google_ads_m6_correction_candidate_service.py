"""Stage validated M6 correction candidates WITHOUT replacing original RAW or facts.

Internal-only service: no production endpoint invokes this module. A separate
correction RAW intake and canonical promotion require future authorization.
"""
from __future__ import annotations

import os
import sqlalchemy as sa

from app.extensions import db
from app.models.warehouse import WarehouseAuditLogORM
from app.models.google_ads_m6_correction import (
    GoogleAdsM6CorrectionCaseORM as Case,
    GoogleAdsM6CorrectionCampaignORM as Campaign,
    GoogleAdsM6CorrectionGroupORM as Group,
)
from app.warehouse.services.google_ads_m6_manual_preview_service import (
    require_current_admicorp,
)
from app.warehouse.services.google_ads_m6_manual_structured_service import (
    CUSTOMER_ID, CAMPAIGN_TYPE, GROUP_TYPE, _approval, _load_pair,
    _campaign_record, _group_record, _customer_id,
    GoogleAdsM6ManualStructuredError,
)
from app.warehouse.services.google_ads_daily_ingestion_service import (
    GoogleAdsDailyIngestionError,
)

FLAG = "GOOGLE_ADS_M6_CORRECTION_CANDIDATE_ENABLED"
AUDIT = "GA_M6_CORRECTION_CANDIDATE"
ORIGIN = "google_ads_correction_pair"


class GoogleAdsM6CorrectionStageError(RuntimeError):
    """Non-sensitive, fixed machine codes only."""


def _check(ok, code):
    if not ok:
        raise GoogleAdsM6CorrectionStageError(code)


def _candidate_campaign(row, case_id):
    base = _campaign_record(row, 1)
    return {key: base[key] for key in (
        "campaign_key", "campaign_name", "currency_code", "cost",
        "impressions", "clicks", "conversions", "conversion_value",
    )} | {"case_id": case_id}


def _candidate_group(row, case_id):
    base = _group_record(row, 1)
    return {key: base[key] for key in (
        "campaign_key", "ad_group_key", "campaign_name", "ad_group_name",
        "currency_code", "cost", "impressions", "clicks", "conversions",
        "free_pass_conversions", "web_purchase_conversions", "conversion_value",
    )} | {"case_id": case_id}


def _authorized_operator(conn, actor_id):
    row = conn.execute(sa.text("""
        SELECT u.username, u.rol, o.can_upload
        FROM users u LEFT JOIN warehouse_operators o ON o.user_id = u.id
        WHERE u.id = :id FOR UPDATE OF u
    """), {"id": actor_id}).mappings().one_or_none()
    _check(
        row is not None
        and str(row["username"]).strip().casefold() == "admicorp"
        and str(row["rol"]).strip().upper() == "ADMINISTRADOR"
        and row["can_upload"] is True,
        "FORBIDDEN",
    )


def _correction_raw_provenance(conn, *, upload_id, kind, actor, day, hashes):
    data = conn.execute(sa.text("""
        SELECT u.status, u.uploaded_by_user_id, u.file_hash_sha256,
               u.cutoff_date, u.date_from, u.date_to,
               u.source_file_deleted_at, rt.key AS kind
        FROM warehouse_uploads u JOIN warehouse_report_types rt
          ON rt.id = u.report_type_id
        WHERE u.id = :id FOR SHARE OF u
    """), {"id": upload_id}).mappings().one_or_none()
    expected_sha = hashes[0] if kind == CAMPAIGN_TYPE else hashes[1]
    _check(
        data is not None and data["kind"] == kind
        and data["status"] == "ACTIVE"
        and data["uploaded_by_user_id"] == actor
        and data["file_hash_sha256"] == expected_sha
        and data["cutoff_date"] == data["date_from"] == data["date_to"] == day
        and data["source_file_deleted_at"] is None,
        "CORRECTION_RAW_INVALID",
    )
    audits = conn.execute(sa.text("""
        SELECT performed_by_user_id, details FROM warehouse_audit_logs
        WHERE upload_id = :id AND action = 'UPLOAD'
    """), {"id": upload_id}).mappings().all()
    _check(len(audits) == 1, "CORRECTION_RAW_PROVENANCE_INVALID")
    audit = audits[0]
    details = audit["details"]
    _check(
        audit["performed_by_user_id"] == actor
        and isinstance(details, dict)
        and details.get("upload_origin") == ORIGIN
        and details.get("correction_case_intent") == "CANDIDATE_ONLY"
        and details.get("manual_pair_business_date") == day.isoformat()
        and details.get("manual_pair_campaign_sha256") == hashes[0]
        and details.get("manual_pair_group_sha256") == hashes[1]
        and details.get("publication") == "NOT_AUTHORIZED",
        "CORRECTION_RAW_PROVENANCE_INVALID",
    )


def _prior_evidence(conn, *, day, campaign_id, group_id):
    rows = conn.execute(sa.text("""
        SELECT rt.key AS kind
        FROM warehouse_uploads u JOIN warehouse_report_types rt
          ON rt.id = u.report_type_id
        WHERE u.id NOT IN (:campaign, :groups)
          AND u.cutoff_date = :day
          AND u.date_from = :day AND u.date_to = :day
          AND rt.key IN ('google_ads_campaign_daily',
                         'google_ads_ad_group_daily')
    """), {"campaign": campaign_id, "groups": group_id, "day": day}).scalars().all()
    _check({CAMPAIGN_TYPE, GROUP_TYPE} <= set(rows),
           "CORRECTION_PRIOR_RAW_REQUIRED")


def _canonical(conn, day):
    rows = conn.execute(sa.text("""
        SELECT id, revision, campaign_upload_id, ad_group_upload_id,
               is_canonical
        FROM google_ads_m6_daily_publications
        WHERE customer_id = :customer AND business_date = :day
        FOR UPDATE
    """), {"customer": CUSTOMER_ID, "day": day}).mappings().all()
    canonical = [r for r in rows if r["is_canonical"]]
    _check(len(canonical) <= 1, "CORRECTION_CANONICAL_CONFLICT")
    _check(not rows or len(canonical) == 1, "CORRECTION_CANONICAL_CONFLICT")
    return canonical[0] if canonical else None


def _matches(conn, table, case_id, expected, keys):
    rows = conn.execute(sa.select(*[table.c[k] for k in expected[0]])
                        .where(table.c.case_id == case_id)).mappings().all()
    actual = {tuple(r[k] for k in keys): dict(r) for r in rows}
    wanted = {tuple(r[k] for k in keys): r for r in expected}
    _check(len(rows) == len(actual) == len(wanted) and actual == wanted,
           "CORRECTION_CANDIDATE_CONFLICT")


def _audits_match(conn, case_id, actor, day, revision, campaign_id, group_id,
                  version_id):
    rows = conn.execute(sa.text("""
        SELECT upload_id, performed_by_user_id, details
        FROM warehouse_audit_logs
        WHERE action = :action AND upload_id IN (:campaign, :groups)
    """), {"action": AUDIT, "campaign": campaign_id, "groups": group_id}).mappings().all()
    _check(len(rows) == 2 and {r["upload_id"] for r in rows} ==
           {campaign_id, group_id}, "CORRECTION_CANDIDATE_CONFLICT")
    for row in rows:
        d = row["details"]
        _check(
            row["performed_by_user_id"] == actor and isinstance(d, dict)
            and d.get("case_id") == case_id and d.get("revision") == revision
            and d.get("customer_id") == CUSTOMER_ID
            and d.get("day") == day.isoformat()
            and d.get("approval_version_id") == version_id
            and d.get("campaign_upload_id") == campaign_id
            and d.get("ad_group_upload_id") == group_id
            and d.get("publication") == "NOT_AUTHORIZED",
            "CORRECTION_CANDIDATE_CONFLICT",
        )


def stage_m6_correction_candidate(*, campaign_upload_id: int,
                                  group_upload_id: int, revision: int,
                                  reason: str,
                                  expected_publication_id: int | None = None):
    """JWT-bound ADMICORP service, fail-closed; never changes canonical rows."""
    if os.environ.get(FLAG, "").strip().lower() != "true":
        raise GoogleAdsM6CorrectionStageError("CORRECTION_CANDIDATE_DISABLED")
    _check(
        type(campaign_upload_id) is int and campaign_upload_id > 0
        and type(group_upload_id) is int and group_upload_id > 0
        and campaign_upload_id != group_upload_id
        and type(revision) is int and revision > 0
        and (expected_publication_id is None or
             (type(expected_publication_id) is int and expected_publication_id > 0))
        and isinstance(reason, str) and 10 <= len(reason.strip()) <= 500,
        "INVALID_CORRECTION_CANDIDATE",
    )
    try:
        actor = require_current_admicorp()  # JWT identity + current users DB
    except Exception:
        raise GoogleAdsM6CorrectionStageError("FORBIDDEN") from None
    try:
        _check(_customer_id() == CUSTOMER_ID, "GOOGLE_ADS_CUSTOMER_NOT_READY")
    except GoogleAdsDailyIngestionError:
        raise GoogleAdsM6CorrectionStageError("GOOGLE_ADS_CUSTOMER_NOT_READY") from None

    try:
        campaign, groups, summary, mapping, hashes = _load_pair(
            campaign_upload_id, group_upload_id)
    except GoogleAdsM6ManualStructuredError:
        raise GoogleAdsM6CorrectionStageError("CORRECTION_RAW_PAIR_REJECTED") from None
    day = campaign.date_from
    _check(len(campaign.rows) == 27 and len(groups.rows) == 43,
           "CORRECTION_RAW_PAIR_REJECTED")

    with db.engine.begin() as conn:
        # Reuse day-level lock of original staging/publishing; never race a day.
        conn.execute(sa.text("""
            SELECT pg_advisory_xact_lock(
                hashtext('google_ads_m6_manual_structured_pair'),
                CAST(:ordinal AS INTEGER))
        """), {"ordinal": day.toordinal()})
        _authorized_operator(conn, actor)
        version_id = _approval(conn, day, mapping)
        for upload_id, kind in (
            (campaign_upload_id, CAMPAIGN_TYPE),
            (group_upload_id, GROUP_TYPE),
        ):
            _correction_raw_provenance(
                conn, upload_id=upload_id, kind=kind,
                actor=actor, day=day, hashes=hashes,
            )
        _prior_evidence(conn, day=day, campaign_id=campaign_upload_id,
                        group_id=group_upload_id)
        canonical = _canonical(conn, day)
        if canonical is None:
            _check(revision == 1 and expected_publication_id is None,
                   "CORRECTION_REVISION_MISMATCH")
        else:
            _check(
                revision == canonical["revision"] + 1
                and expected_publication_id == canonical["id"]
                and canonical["campaign_upload_id"] != campaign_upload_id
                and canonical["ad_group_upload_id"] != group_upload_id,
                "CORRECTION_REVISION_MISMATCH",
            )

        prior = conn.execute(sa.text("""
            SELECT id, revision, expected_publication_id, campaign_upload_id,
                   ad_group_upload_id, approval_version_id, campaign_sha256,
                   ad_group_sha256, requested_by_user_id, reason
            FROM google_ads_m6_correction_cases
            WHERE customer_id = :customer AND business_date = :day
            FOR UPDATE
        """), {"customer": CUSTOMER_ID, "day": day}).mappings().all()
        for old in prior:
            if old["revision"] == revision:
                _check(
                    old["expected_publication_id"] == expected_publication_id
                    and old["campaign_upload_id"] == campaign_upload_id
                    and old["ad_group_upload_id"] == group_upload_id
                    and old["approval_version_id"] == version_id
                    and (old["campaign_sha256"], old["ad_group_sha256"]) == hashes
                    and old["requested_by_user_id"] == actor
                    and old["reason"] == reason.strip(),
                    "CORRECTION_CANDIDATE_CONFLICT",
                )
                cid = int(old["id"])
                wanted_c = [_candidate_campaign(r, cid) for r in campaign.rows]
                wanted_g = [_candidate_group(r, cid) for r in groups.rows]
                _matches(conn, Campaign.__table__, cid, wanted_c,
                         ("campaign_key",))
                _matches(conn, Group.__table__, cid, wanted_g,
                         ("campaign_key", "ad_group_key"))
                _audits_match(conn, cid, actor, day, revision,
                              campaign_upload_id, group_upload_id, version_id)
                return {
                    "status": "ALREADY_STAGED", "case_id": cid,
                    "revision": revision, "business_date": day.isoformat(),
                    "campaign_rows": len(wanted_c), "group_rows": len(wanted_g),
                    "eligible_for_publication": False,
                    "funnel_publication": "NOT_AUTHORIZED",
                }
            _check(old["revision"] <= (canonical["revision"] if canonical else 0),
                   "CORRECTION_CANDIDATE_CONFLICT")

        cid = int(conn.execute(Case.__table__.insert().values(
            customer_id=CUSTOMER_ID, business_date=day, revision=revision,
            expected_publication_id=expected_publication_id,
            campaign_upload_id=campaign_upload_id,
            ad_group_upload_id=group_upload_id,
            approval_version_id=version_id,
            campaign_sha256=hashes[0], ad_group_sha256=hashes[1],
            requested_by_user_id=actor, reason=reason.strip(),
        ).returning(Case.id)).scalar_one())
        wanted_c = [_candidate_campaign(r, cid) for r in campaign.rows]
        wanted_g = [_candidate_group(r, cid) for r in groups.rows]
        conn.execute(Campaign.__table__.insert(), wanted_c)
        conn.execute(Group.__table__.insert(), wanted_g)
        for upload_id, kind, count in (
            (campaign_upload_id, CAMPAIGN_TYPE, len(wanted_c)),
            (group_upload_id, GROUP_TYPE, len(wanted_g)),
        ):
            conn.execute(WarehouseAuditLogORM.__table__.insert().values(
                upload_id=upload_id, action=AUDIT,
                performed_by_user_id=actor,
                details={
                    "case_id": cid, "revision": revision,
                    "customer_id": CUSTOMER_ID, "day": day.isoformat(),
                    "approval_version_id": version_id,
                    "campaign_upload_id": campaign_upload_id,
                    "ad_group_upload_id": group_upload_id,
                    "report_type_key": kind,
                    "rows_created": count,
                    "publication": "NOT_AUTHORIZED",
                },
            ))
    return {
        "status": "CANDIDATE_STAGED", "case_id": cid,
        "revision": revision, "business_date": day.isoformat(),
        "campaign_rows": len(wanted_c), "group_rows": len(wanted_g),
        "account_cost_mxn": summary["account_cost_mxn"],
        "branch_cost_mxn": summary["branch_cost_mxn"],
        "unassigned_cost_mxn": summary["unassigned_cost_mxn"],
        "eligible_for_publication": False,
        "funnel_publication": "NOT_AUTHORIZED",
    }
