"""Read-only M6 correction case comparison, never authorization or promotion."""
from __future__ import annotations

from decimal import Decimal
import sqlalchemy as sa

from app.extensions import db
from app.warehouse.services.google_ads_m6_continuity_approval_service import CUSTOMER_ID


class GoogleAdsM6CorrectionReviewError(RuntimeError):
    pass


def inspect_correction_case(case_id: int) -> dict:
    """Case-by-case financial comparison for authorized ADMICORP review."""
    if type(case_id) is not int or case_id <= 0:
        raise GoogleAdsM6CorrectionReviewError("INVALID_CORRECTION_CASE")
    with db.engine.connect() as conn:
        with conn.begin():
            conn.execute(sa.text("SET TRANSACTION READ ONLY"))
            case = conn.execute(sa.text("""
                SELECT id, business_date, revision, campaign_upload_id,
                       ad_group_upload_id, approval_version_id,
                       expected_publication_id, requested_by_user_id,
                       reason, campaign_sha256, ad_group_sha256
                FROM google_ads_m6_correction_cases
                WHERE id = :id AND customer_id = :customer
            """), {"id": case_id, "customer": CUSTOMER_ID}).mappings().one_or_none()
            if case is None:
                raise GoogleAdsM6CorrectionReviewError("CORRECTION_CASE_NOT_FOUND")
            camp = conn.execute(sa.text("""
                SELECT campaign_key, cost, clicks, impressions, conversions
                FROM google_ads_m6_correction_campaign_facts
                WHERE case_id = :id ORDER BY campaign_key
            """), {"id": case_id}).mappings().all()
            group = conn.execute(sa.text("""
                SELECT campaign_key, ad_group_key, cost, clicks, impressions,
                       conversions, free_pass_conversions, web_purchase_conversions
                FROM google_ads_m6_correction_group_facts
                WHERE case_id = :id ORDER BY campaign_key, ad_group_key
            """), {"id": case_id}).mappings().all()
            mapped = conn.execute(sa.text("""
                SELECT i.campaign_key, i.ad_group_key, i.sucursal_canon
                FROM google_ads_branch_approved_identities i
                WHERE i.approval_version_id = :version
            """), {"version": case["approval_version_id"]}).mappings().all()
            # Compare ONLY with the exact canonical publication being
            # superseded. Revision 3 must compare with revision 2, not an
            # orphaned original campaign ledger or another upload for the day.
            baseline = None
            if case["expected_publication_id"] is not None:
                prior_pub = conn.execute(sa.text("""
                    SELECT p.id, p.campaign_upload_id,
                           x.case_id AS correction_case_id
                    FROM google_ads_m6_daily_publications p
                    LEFT JOIN google_ads_m6_correction_promotions x
                      ON x.publication_id = p.id
                    WHERE p.id = :prior_id
                      AND p.customer_id = :customer
                      AND p.business_date = :day
                """), {
                    "prior_id": case["expected_publication_id"],
                    "customer": CUSTOMER_ID, "day": case["business_date"],
                }).mappings().one_or_none()
                if prior_pub:
                    if prior_pub["correction_case_id"] is not None:
                        baseline = conn.execute(sa.text("""
                            SELECT COUNT(*) AS n, SUM(cost) AS amount
                            FROM google_ads_m6_correction_campaign_facts
                            WHERE case_id = :prior_case
                        """), {"prior_case": prior_pub["correction_case_id"]}).mappings().one()
                    else:
                        baseline = conn.execute(sa.text("""
                            SELECT COUNT(*) AS n, SUM(cost) AS amount
                            FROM google_ads_daily_metrics
                            WHERE customer_id = :customer AND report_date = :day
                              AND source_upload_id = :prior_upload
                        """), {
                            "customer": CUSTOMER_ID,
                            "day": case["business_date"],
                            "prior_upload": prior_pub["campaign_upload_id"],
                        }).mappings().one()
            live = conn.execute(sa.text("""
                SELECT id, revision, is_canonical FROM
                    google_ads_m6_daily_publications
                WHERE customer_id = :customer AND business_date = :day
            """), {"customer": CUSTOMER_ID, "day": case["business_date"]}).mappings().all()
            review = conn.execute(sa.text("""
                SELECT id, decision, reviewed_by_user_id, snapshot_sha256,
                       review_note
                FROM google_ads_m6_correction_decisions
                WHERE case_id = :id
            """), {"id": case_id}).mappings().one_or_none()
            promotion = conn.execute(sa.text("""
                SELECT publication_id, promoted_by_user_id, snapshot_sha256
                FROM google_ads_m6_correction_promotions
                WHERE case_id = :id
            """), {"id": case_id}).mappings().one_or_none()
    mapping = {(r["campaign_key"], r["ad_group_key"]): r["sucursal_canon"]
               for r in mapped}
    campaign_cost = sum((Decimal(r["cost"]) for r in camp), Decimal("0"))
    group_cost = sum((Decimal(r["cost"]) for r in group), Decimal("0"))
    branch_costs = {}
    for row in group:
        branch = mapping.get((row["campaign_key"], row["ad_group_key"]))
        if branch:
            branch_costs[branch] = branch_costs.get(branch, Decimal("0")) + Decimal(row["cost"])
    assigned = sum(branch_costs.values(), Decimal("0"))
    prior_cost = (
        Decimal(baseline["amount"]) if baseline is not None
        and int(baseline["n"]) == 27 and baseline["amount"] is not None
        else None
    )
    diff = campaign_cost - prior_cost if prior_cost is not None else None
    current = [r for r in live if r["is_canonical"]]
    is_published = bool(promotion and len(current) == 1
                        and current[0]["id"] == promotion["publication_id"]
                        and promotion["snapshot_sha256"] == (
                            review["snapshot_sha256"] if review else None))
    status = (
        "CANONICAL_PUBLISHED" if is_published
        else "INCOMPLETE_CANDIDATE" if len(camp) != 27 or len(group) != 43
        else "RECONCILIATION_FAILED" if campaign_cost != group_cost
        else "CANONICAL_CHANGED" if len(current) != 1 and case["expected_publication_id"] is not None
        else "CANONICAL_CHANGED" if len(current) == 1 and (
            current[0]["id"] != case["expected_publication_id"]
            or current[0]["revision"] + 1 != case["revision"])
        else "REQUIRES_INDEPENDENT_REVIEW" if prior_cost is not None
        else "REQUIRES_BASELINE_EVIDENCE_REVIEW"
    )
    return {
        "case_id": int(case_id), "business_date": case["business_date"].isoformat(),
        "revision": case["revision"],
        "expected_publication_id": case["expected_publication_id"],
        "requested_by_user_id": case["requested_by_user_id"],
        "reason": case["reason"],
        "campaign_upload_id": case["campaign_upload_id"],
        "ad_group_upload_id": case["ad_group_upload_id"],
        "campaign_rows": len(camp), "group_rows": len(group),
        "candidate_account_cost_mxn": str(campaign_cost),
        "candidate_assigned_cost_mxn": str(assigned),
        "candidate_unassigned_cost_mxn": str(campaign_cost - assigned),
        "previous_account_cost_mxn": str(prior_cost) if prior_cost is not None else None,
        "delta_account_cost_mxn": str(diff) if diff is not None else None,
        "branch_costs_mxn": [
            {"sucursal_canon": branch, "cost_mxn": str(amount)}
            for branch, amount in sorted(branch_costs.items())
        ],
        "status": status,
        "approved": bool(review and review["decision"] == "APPROVED"),
        "decision": {
            "decision_id": review["id"],
            "decision": review["decision"],
            "reviewed_by_user_id": review["reviewed_by_user_id"],
            "snapshot_sha256": review["snapshot_sha256"],
        } if review else None,
        "promotion": {
            "publication_id": promotion["publication_id"],
            "promoted_by_user_id": promotion["promoted_by_user_id"],
        } if promotion else None,
        "eligible_for_publication": False,
        "can_auto_republish": False,
    }
