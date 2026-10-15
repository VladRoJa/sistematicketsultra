"""Atomic versioned M6 correction promotion with two-person approval.

Never modifies original metric rows or Warehouse RAW. A separate link table
references the immutable candidate, independent decision and new publication.
Existing publication row changes only is_canonical True->False in one PG txn.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
import os
import re

import sqlalchemy as sa

from app.extensions import db
from app.models.google_ads_m6_daily_publication import GoogleAdsM6DailyPublicationORM
from app.models.google_ads_m6_correction_promotion import GoogleAdsM6CorrectionPromotionORM
from app.models.warehouse import WarehouseAuditLogORM
from app.warehouse.services.google_ads_m6_correction_decision_service import (
    REVIEWERS, ACTION as REVIEW_AUDIT, _read_snapshot,
    GoogleAdsM6CorrectionDecisionError,
)
from app.warehouse.services.google_ads_m6_manual_preview_service import (
    require_current_admicorp,
)
from app.warehouse.services.google_ads_m6_manual_structured_service import (
    _load_pair, GoogleAdsM6ManualStructuredError,
)
from app.warehouse.services.google_ads_m6_continuity_approval_service import CUSTOMER_ID

FLAG = "GOOGLE_ADS_M6_CORRECTION_PROMOTION_ENABLED"
ACTION = "GA_M6_CORR_PROMOTE"


class GoogleAdsM6CorrectionPromotionError(RuntimeError):
    pass


def _require(ok, code):
    if not ok:
        raise GoogleAdsM6CorrectionPromotionError(code)


def _reviewer_is_current(conn, reviewer):
    allowlist = {
        int(v) for v in os.getenv(REVIEWERS, "").split(",")
        if re.fullmatch(r"[1-9][0-9]*", v.strip())
    }
    principal = conn.execute(sa.text("""
        SELECT u.rol, o.can_view
        FROM users u LEFT JOIN warehouse_operators o ON o.user_id = u.id
        WHERE u.id = :id FOR SHARE OF u
    """), {"id": reviewer}).mappings().one_or_none()
    return (
        reviewer in allowlist and principal is not None
        and str(principal["rol"]).strip().upper() == "ADMINISTRADOR"
        and principal["can_view"] is True
    )


def _review_audit_valid(conn, case, decision, digest):
    rows = conn.execute(sa.text("""
        SELECT upload_id, performed_by_user_id, details
        FROM warehouse_audit_logs
        WHERE action = :action AND
              upload_id IN (:campaign, :groups)
    """), {
        "action": REVIEW_AUDIT,
        "campaign": case["campaign_upload_id"],
        "groups": case["ad_group_upload_id"],
    }).mappings().all()
    if len(rows) != 2 or {r["upload_id"] for r in rows} != {
        case["campaign_upload_id"], case["ad_group_upload_id"],
    }:
        return False
    for row in rows:
        d = row["details"]
        if not (
            row["performed_by_user_id"] == decision["reviewed_by_user_id"]
            and isinstance(d, dict)
            and d.get("case_id") == case["id"]
            and d.get("decision_id") == decision["id"]
            and d.get("decision") == "APPROVED"
            and d.get("snapshot_sha256") == digest
            and d.get("publication") == "NOT_AUTHORIZED"
        ):
            return False
    return True


def _verify_audited_approval(conn, case, digest, decision_id, actor):
    decision = conn.execute(sa.text("""
        SELECT id, case_id, reviewed_by_user_id, decision, snapshot_sha256
        FROM google_ads_m6_correction_decisions
        WHERE case_id = :case AND id = :id FOR SHARE
    """), {"case": case["id"], "id": decision_id}).mappings().one_or_none()
    _require(
        decision is not None
        and decision["decision"] == "APPROVED"
        and decision["snapshot_sha256"] == digest
        and decision["reviewed_by_user_id"] not in (
            actor, case["requested_by_user_id"])
        and _reviewer_is_current(conn, decision["reviewed_by_user_id"])
        and _review_audit_valid(conn, case, decision, digest),
        "CORRECTION_INDEPENDENT_APPROVAL_REQUIRED",
    )
    return decision


def promote_m6_correction(*, case_id: int, decision_id: int,
                           snapshot_sha256: str, revision: int,
                           expected_publication_id: int | None):
    if os.getenv(FLAG, "").strip().lower() != "true":
        raise GoogleAdsM6CorrectionPromotionError("CORRECTION_PROMOTION_DISABLED")
    _require(
        type(case_id) is int and case_id > 0
        and type(decision_id) is int and decision_id > 0
        and type(revision) is int and revision > 0
        and (expected_publication_id is None
             or (type(expected_publication_id) is int
                 and expected_publication_id > 0))
        and isinstance(snapshot_sha256, str)
        and re.fullmatch(r"[a-f0-9]{64}", snapshot_sha256),
        "INVALID_CORRECTION_PROMOTION",
    )
    try:
        actor = require_current_admicorp()
    except PermissionError:
        raise GoogleAdsM6CorrectionPromotionError("FORBIDDEN") from None

    # Recheck physical RAW bytes and the frozen 27/43 catalog independently
    # before entering a transaction. The snapshot below locks current DB state.
    with db.engine.connect() as conn:
        seed = conn.execute(sa.text("""
            SELECT business_date, campaign_upload_id, ad_group_upload_id
            FROM google_ads_m6_correction_cases
            WHERE id = :case AND customer_id = :customer
        """), {"case": case_id, "customer": CUSTOMER_ID}).mappings().one_or_none()
    _require(seed is not None, "CORRECTION_CASE_NOT_FOUND")
    try:
        camp, group, _, _, hashes = _load_pair(
            seed["campaign_upload_id"], seed["ad_group_upload_id"]
        )
    except GoogleAdsM6ManualStructuredError:
        raise GoogleAdsM6CorrectionPromotionError("CORRECTION_RAW_UNREADABLE") from None
    _require(
        camp.date_from == camp.date_to == group.date_from == group.date_to
        == seed["business_date"],
        "CORRECTION_DAY_MISMATCH",
    )

    with db.engine.begin() as conn:
        conn.execute(sa.text("""
            SELECT pg_advisory_xact_lock(
                hashtext('google_ads_m6_manual_structured_pair'),
                CAST(:ordinal AS INTEGER))
        """), {"ordinal": seed["business_date"].toordinal()})
        principal = conn.execute(sa.text("""
            SELECT u.username, u.rol, o.can_upload
            FROM users u LEFT JOIN warehouse_operators o ON o.user_id = u.id
            WHERE u.id = :id FOR UPDATE OF u
        """), {"id": actor}).mappings().one_or_none()
        _require(
            principal is not None
            and str(principal["username"]).strip().casefold() == "admicorp"
            and str(principal["rol"]).strip().upper() == "ADMINISTRADOR"
            and principal["can_upload"] is True,
            "FORBIDDEN",
        )
        promotion = conn.execute(sa.text("""
            SELECT id, case_id, publication_id, decision_id,
                   superseded_publication_id, promoted_by_user_id,
                   snapshot_sha256
            FROM google_ads_m6_correction_promotions
            WHERE case_id = :case FOR UPDATE
        """), {"case": case_id}).mappings().one_or_none()
        try:
            case, digest, stats = _read_snapshot(
                conn, case_id,
                promoted_publication_id=(
                    promotion["publication_id"] if promotion else None
                ),
            )
        except GoogleAdsM6CorrectionDecisionError as exc:
            raise GoogleAdsM6CorrectionPromotionError(str(exc)) from None
        _require(
            case["revision"] == revision
            and case["expected_publication_id"] == expected_publication_id
            and digest == snapshot_sha256
            and hashes == (case["campaign_sha256"], case["ad_group_sha256"]),
            "CORRECTION_SNAPSHOT_CHANGED",
        )
        _verify_audited_approval(conn, case, digest, decision_id, actor)
        if promotion is not None:
            _require(
                promotion["decision_id"] == decision_id
                and promotion["snapshot_sha256"] == digest
                and promotion["promoted_by_user_id"] == actor
                and promotion["superseded_publication_id"]
                    == expected_publication_id,
                "CORRECTION_PROMOTION_CONFLICT",
            )
            return {
                "status": "ALREADY_PROMOTED", "case_id": case_id,
                "publication_id": promotion["publication_id"],
                "revision": revision, "snapshot_sha256": digest,
                "business_date": case["business_date"].isoformat(),
                "is_canonical": True, **stats,
            }
        if expected_publication_id is not None:
            old = conn.execute(sa.text("""
                UPDATE google_ads_m6_daily_publications
                   SET is_canonical = false
                 WHERE id = :prior AND customer_id = :customer
                   AND business_date = :day AND revision = :old_revision
                   AND is_canonical = true
                RETURNING id
            """), {
                "prior": expected_publication_id, "customer": CUSTOMER_ID,
                "day": case["business_date"], "old_revision": revision - 1,
            }).scalar_one_or_none()
            _require(old == expected_publication_id,
                     "CORRECTION_CANONICAL_CHANGED")
        else:
            count = conn.execute(sa.text("""
                SELECT count(*) FROM google_ads_m6_daily_publications
                WHERE customer_id = :customer AND business_date = :day
            """), {"customer": CUSTOMER_ID,
                   "day": case["business_date"]}).scalar_one()
            _require(count == 0 and revision == 1,
                     "CORRECTION_CANONICAL_CHANGED")
        pub_id = int(conn.execute(
            GoogleAdsM6DailyPublicationORM.__table__.insert().values(
                customer_id=CUSTOMER_ID,
                business_date=case["business_date"], revision=revision,
                campaign_upload_id=case["campaign_upload_id"],
                ad_group_upload_id=case["ad_group_upload_id"],
                approval_version_id=case["approval_version_id"],
                campaign_sha256=hashes[0], ad_group_sha256=hashes[1],
                is_canonical=True, published_by_user_id=actor,
                published_on=datetime.now(ZoneInfo("America/Tijuana")).date(),
            ).returning(GoogleAdsM6DailyPublicationORM.id)
        ).scalar_one())
        conn.execute(
            GoogleAdsM6CorrectionPromotionORM.__table__.insert().values(
                case_id=case_id, publication_id=pub_id, decision_id=decision_id,
                superseded_publication_id=expected_publication_id,
                promoted_by_user_id=actor, snapshot_sha256=digest,
            )
        )
        for uid in (case["campaign_upload_id"], case["ad_group_upload_id"]):
            conn.execute(WarehouseAuditLogORM.__table__.insert().values(
                upload_id=uid, action=ACTION, performed_by_user_id=actor,
                details={
                    "case_id": case_id, "decision_id": decision_id,
                    "publication_id": pub_id, "revision": revision,
                    "superseded_publication_id": expected_publication_id,
                    "snapshot_sha256": digest,
                    "customer_id": CUSTOMER_ID,
                    "business_date": case["business_date"].isoformat(),
                    "is_canonical": True,
                },
            ))
        return {
            "status": "CORRECTION_CANONICAL_PROMOTED",
            "case_id": case_id, "decision_id": decision_id,
            "publication_id": pub_id, "revision": revision,
            "snapshot_sha256": digest,
            "business_date": case["business_date"].isoformat(),
            "is_canonical": True, **stats,
        }
