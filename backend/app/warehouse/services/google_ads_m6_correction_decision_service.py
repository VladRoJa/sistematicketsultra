"""Independent, append-only approval for an exact M6 correction fact snapshot.

No canonical writes and no Funnel reader changes. Review and future promotion
MUST independently recompute the digest and verify current canonical/raw state.
"""
from __future__ import annotations

from decimal import Decimal
from hashlib import sha256
import json
import os
import re

import sqlalchemy as sa
from flask_jwt_extended import get_jwt_identity

from app.extensions import db
from app.models.google_ads_m6_correction_decision import GoogleAdsM6CorrectionDecisionORM
from app.models.warehouse import WarehouseAuditLogORM
from app.warehouse.services.google_ads_m6_continuity_approval_service import CUSTOMER_ID

FLAG = "GOOGLE_ADS_M6_CORRECTION_REVIEW_ENABLED"
REVIEWERS = "GOOGLE_ADS_M6_CORRECTION_REVIEWER_USER_IDS"
ACTION = "GA_M6_CORR_REVIEW"
CAMPAIGN_COLUMNS = (
    "campaign_key", "campaign_name", "currency_code", "cost",
    "impressions", "clicks", "conversions", "conversion_value",
)
GROUP_COLUMNS = (
    "campaign_key", "ad_group_key", "campaign_name", "ad_group_name",
    "currency_code", "cost", "impressions", "clicks", "conversions",
    "free_pass_conversions", "web_purchase_conversions", "conversion_value",
)


class GoogleAdsM6CorrectionDecisionError(RuntimeError):
    """Fixed non-sensitive refusal code."""


def _ensure(ok, code):
    if not ok:
        raise GoogleAdsM6CorrectionDecisionError(code)


def _actor(conn):
    try:
        actor = int(get_jwt_identity())
    except (ValueError, TypeError):
        raise GoogleAdsM6CorrectionDecisionError("FORBIDDEN") from None
    config = os.getenv(REVIEWERS, "")
    # Deny-by-default, explicit numeric allowlist, no stars, no open wildcard.
    permitted = {
        int(v) for v in config.split(",") if re.fullmatch(r"[1-9][0-9]*", v.strip())
    }
    _ensure(actor > 0 and actor in permitted, "FORBIDDEN")
    principal = conn.execute(sa.text("""
        SELECT u.rol, o.can_view, o.can_upload
        FROM users u
        LEFT JOIN warehouse_operators o ON o.user_id = u.id
        WHERE u.id = :actor FOR UPDATE OF u
    """), {"actor": actor}).mappings().one_or_none()
    _ensure(
        principal is not None
        and str(principal["rol"]).strip().upper() == "ADMINISTRADOR"
        and principal["can_view"] is True,
        "FORBIDDEN",
    )
    return actor


def _read_snapshot(conn, case_id):
    case = conn.execute(sa.text("""
        SELECT id, customer_id, business_date, revision,
               expected_publication_id, campaign_upload_id,
               ad_group_upload_id, campaign_sha256, ad_group_sha256,
               approval_version_id, requested_by_user_id, reason
        FROM google_ads_m6_correction_cases
        WHERE id = :id AND customer_id = :customer FOR UPDATE
    """), {"id": case_id, "customer": CUSTOMER_ID}).mappings().one_or_none()
    _ensure(case is not None, "CORRECTION_CASE_NOT_FOUND")
    canonical = conn.execute(sa.text("""
        SELECT id, revision, approval_version_id
        FROM google_ads_m6_daily_publications
        WHERE customer_id = :customer AND business_date = :day
          AND is_canonical = true FOR SHARE
    """), {"customer": CUSTOMER_ID, "day": case["business_date"]}).mappings().all()
    _ensure(len(canonical) <= 1, "CORRECTION_CANONICAL_CONFLICT")
    if canonical:
        _ensure(
            case["expected_publication_id"] == canonical[0]["id"]
            and case["revision"] == canonical[0]["revision"] + 1,
            "CORRECTION_CANONICAL_CHANGED",
        )
    else:
        _ensure(
            case["expected_publication_id"] is None and case["revision"] == 1,
            "CORRECTION_CANONICAL_CHANGED",
        )
    source = conn.execute(sa.text("""
        SELECT id, status, file_hash_sha256, cutoff_date,
               date_from, date_to, source_file_deleted_at
        FROM warehouse_uploads
        WHERE id IN (:campaign, :groups) FOR SHARE
    """), {"campaign": case["campaign_upload_id"],
           "groups": case["ad_group_upload_id"]}).mappings().all()
    by_id = {r["id"]: r for r in source}
    _ensure(len(by_id) == 2, "CORRECTION_RAW_INVALID")
    for uid, digest in (
        (case["campaign_upload_id"], case["campaign_sha256"]),
        (case["ad_group_upload_id"], case["ad_group_sha256"]),
    ):
        raw = by_id[uid]
        _ensure(
            raw["status"] == "ACTIVE" and raw["source_file_deleted_at"] is None
            and raw["file_hash_sha256"] == digest
            and raw["date_from"] == raw["date_to"] == raw["cutoff_date"]
            == case["business_date"],
            "CORRECTION_RAW_INVALID",
        )
    campaign = conn.execute(sa.text("""
        SELECT campaign_key, campaign_name, currency_code, cost,
               impressions, clicks, conversions, conversion_value
        FROM google_ads_m6_correction_campaign_facts
        WHERE case_id = :id ORDER BY campaign_key FOR SHARE
    """), {"id": case_id}).mappings().all()
    groups = conn.execute(sa.text("""
        SELECT campaign_key, ad_group_key, campaign_name, ad_group_name,
               currency_code, cost, impressions, clicks, conversions,
               free_pass_conversions, web_purchase_conversions, conversion_value
        FROM google_ads_m6_correction_group_facts
        WHERE case_id = :id ORDER BY campaign_key, ad_group_key FOR SHARE
    """), {"id": case_id}).mappings().all()
    _ensure(len(campaign) == 27 and len(groups) == 43,
            "CORRECTION_INCOMPLETE_CANDIDATE")
    _ensure(len({r["campaign_key"] for r in campaign}) == 27
            and len({(r["campaign_key"], r["ad_group_key"]) for r in groups}) == 43,
            "CORRECTION_DUPLICATE_FACT")
    amounts = (
        sum((Decimal(r["cost"]) for r in campaign), Decimal("0")),
        sum((Decimal(r["cost"]) for r in groups), Decimal("0")),
    )
    _ensure(amounts[0] == amounts[1], "CORRECTION_RECONCILIATION_FAILED")
    for metric in ("clicks", "impressions"):
        _ensure(
            sum(int(r[metric]) for r in campaign)
            == sum(int(r[metric]) for r in groups),
            "CORRECTION_RECONCILIATION_FAILED",
        )
    _ensure(
        abs(sum(Decimal(r["conversions"]) for r in campaign)
            - sum(Decimal(r["conversions"]) for r in groups))
        <= Decimal("0.01"),
        "CORRECTION_RECONCILIATION_FAILED",
    )
    _ensure(
        all(r["currency_code"] == "MXN" for r in campaign)
        and all(r["currency_code"] == "MXN" for r in groups),
        "CORRECTION_CURRENCY_INVALID",
    )
    mapping = conn.execute(sa.text("""
        SELECT campaign_key, ad_group_key, sucursal_canon
        FROM google_ads_branch_approved_identities
        WHERE approval_version_id = :version
        ORDER BY campaign_key, ad_group_key FOR SHARE
    """), {"version": case["approval_version_id"]}).mappings().all()
    valid_pairs = {(g["campaign_key"], g["ad_group_key"]) for g in groups}
    _ensure(
        len(mapping) == 26 and len({r["sucursal_canon"] for r in mapping}) == 26
        and all((r["campaign_key"], r["ad_group_key"]) in valid_pairs
                for r in mapping),
        "CORRECTION_APPROVED_IDENTITIES_INVALID",
    )
    def _normalize(rows, columns):
        return [[str(r[k]) if isinstance(r[k], Decimal) else r[k] for k in columns]
                for r in rows]
    payload = {
        "case": {
            k: (v.isoformat() if hasattr(v, "isoformat") else v)
            for k, v in dict(case).items()
        },
        "campaigns": _normalize(campaign, CAMPAIGN_COLUMNS),
        "groups": _normalize(groups, GROUP_COLUMNS),
        "mapping": [list(r.values()) for r in mapping],
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=False)
    return case, sha256(serialized.encode("utf-8")).hexdigest(), {
        "campaign_rows": len(campaign), "group_rows": len(groups),
        "account_cost_mxn": str(amounts[0]),
    }


def decide_m6_correction(*, case_id: int, decision: str, note: str):
    """Require a separately allowlisted ADMINISTRADOR; atomic append-only audit."""
    if os.getenv(FLAG, "").strip().lower() != "true":
        raise GoogleAdsM6CorrectionDecisionError("CORRECTION_REVIEW_DISABLED")
    _ensure(type(case_id) is int and case_id > 0
            and decision in ("APPROVED", "REJECTED")
            and isinstance(note, str) and 10 <= len(note.strip()) <= 1000,
            "INVALID_CORRECTION_DECISION")
    with db.engine.begin() as conn:
        # All candidate writes and promotions will use this day/case lock.
        actor = _actor(conn)
        case, digest, stats = _read_snapshot(conn, case_id)
        _ensure(actor != case["requested_by_user_id"],
                "CORRECTION_SELF_REVIEW_FORBIDDEN")
        previous = conn.execute(sa.text("""
            SELECT id, reviewed_by_user_id, decision, snapshot_sha256, review_note
            FROM google_ads_m6_correction_decisions
            WHERE case_id = :case_id FOR UPDATE
        """), {"case_id": case_id}).mappings().one_or_none()
        if previous:
            _ensure(
                previous["reviewed_by_user_id"] == actor
                and previous["decision"] == decision
                and previous["snapshot_sha256"] == digest
                and previous["review_note"] == note.strip(),
                "CORRECTION_REVIEW_CONFLICT",
            )
            return {
                "status": "ALREADY_REVIEWED", "decision_id": int(previous["id"]),
                "case_id": case_id, "decision": decision,
                "snapshot_sha256": digest, **stats,
                "eligible_for_publication": False,
            }
        row_id = conn.execute(
            GoogleAdsM6CorrectionDecisionORM.__table__.insert()
            .values(case_id=case_id, reviewed_by_user_id=actor,
                    decision=decision, snapshot_sha256=digest,
                    review_note=note.strip())
            .returning(GoogleAdsM6CorrectionDecisionORM.id)
        ).scalar_one()
        for upload_id in (case["campaign_upload_id"], case["ad_group_upload_id"]):
            conn.execute(WarehouseAuditLogORM.__table__.insert().values(
                upload_id=upload_id,
                action=ACTION,
                performed_by_user_id=actor,
                details={
                    "decision_id": int(row_id), "case_id": case_id,
                    "decision": decision, "snapshot_sha256": digest,
                    "expected_publication_id": case["expected_publication_id"],
                    "review_note_sha256": sha256(note.strip().encode()).hexdigest(),
                    "publication": "NOT_AUTHORIZED",
                },
            ))
        return {
            "status": "REVIEW_RECORDED", "decision_id": int(row_id),
            "case_id": case_id, "decision": decision,
            "snapshot_sha256": digest, **stats,
            "eligible_for_publication": False,
        }
