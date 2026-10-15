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
            prior = conn.execute(sa.text("""
                SELECT source_upload_id, COUNT(*) AS n, SUM(cost) AS amount
                FROM google_ads_daily_metrics
                WHERE customer_id = :customer AND report_date = :day
                GROUP BY source_upload_id
            """), {"customer": CUSTOMER_ID, "day": case["business_date"]}).mappings().all()
            live = conn.execute(sa.text("""
                SELECT id, revision, is_canonical FROM
                    google_ads_m6_daily_publications
                WHERE customer_id = :customer AND business_date = :day
            """), {"customer": CUSTOMER_ID, "day": case["business_date"]}).mappings().all()
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
    prior_cost = (Decimal(prior[0]["amount"]) if len(prior) == 1
                  and prior[0]["n"] == 27 else None)
    diff = campaign_cost - prior_cost if prior_cost is not None else None
    current = [r for r in live if r["is_canonical"]]
    status = (
        "INCOMPLETE_CANDIDATE" if len(camp) != 27 or len(group) != 43
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
        "status": status, "approved": False, "eligible_for_publication": False,
        "can_auto_republish": False,
    }
