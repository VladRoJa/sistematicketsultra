"""Issue 856 B3 — read-only evidence coverage and contradiction diagnostics.

Operator-submitted document kinds are NOT API verification. This service never
queries Meta/iVentas and does not feed capacity, preflight, or dispatch.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from app.extensions import db
from app.models.marketing import MarketingCampaignV2ChannelPortfolioEvidenceORM as Evidence
from app.services.marketing_campaign_v2_dispatch_config_service import list_channel_bindings
from app.services.marketing_campaign_v2_portfolio_reference_service import list_portfolio_references

DOCUMENT_KINDS = frozenset(("META_DOCUMENT", "IVENTAS_CONFIRMATION"))
REVIEW_FLAGS = frozenset((
    "MISSING_PORTFOLIO_CATALOG",
    "HISTORICAL_BUSINESS_CHANGE",
    "WABA_CROSS_BUSINESS",
    "MULTIPLE_DEFAULT_BRANCH",
))
STATUSES = frozenset((
    "PENDING", "WITHDRAWN", "DECLARED_UNVERIFIED",
    "DOCUMENTED_UNVERIFIED", "REVIEW_REQUIRED",
))


def build_portfolio_review(
    *, bindings: list[dict[str, Any]], portfolios: list[dict[str, Any]],
    revisions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Pure derivation. All revisions supplied, not the truncated 250-row UI history."""
    active = [
        row for row in bindings
        if row.get("provider") == "IVENTAS"
        and row.get("is_active") is True and row.get("is_default") is True
    ]
    active.sort(key=lambda row: (row["sucursal_canon"], row["provider_channel_id"]))
    portfolio_ids = {row["business_id"] for row in portfolios}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sorted(revisions, key=lambda rev: int(rev["revision_id"]), reverse=True):
        grouped[row["provider_channel_id"]].append(row)

    default_counts = Counter(row["sucursal_id"] for row in active)
    current = {channel: rows[0] for channel, rows in grouped.items() if rows}
    waba_businesses: dict[str, set[str]] = defaultdict(set)
    for binding in active:
        claim = current.get(binding["provider_channel_id"])
        if claim and claim["state"] == "DECLARED" and claim.get("waba_id"):
            waba_businesses[claim["waba_id"]].add(claim["business_id"])

    rows = []
    for binding in active:
        channel = binding["provider_channel_id"]
        history = grouped.get(channel, [])
        latest = current.get(channel)
        flags = []
        state = "PENDING"
        if latest is not None and latest["state"] == "WITHDRAWN":
            state = "WITHDRAWN"
        elif latest is not None and latest["state"] == "DECLARED":
            business_id = latest["business_id"]
            if business_id not in portfolio_ids:
                flags.append("MISSING_PORTFOLIO_CATALOG")
            if len({
                r["business_id"] for r in history
                if r["state"] == "DECLARED" and r.get("business_id")
            }) > 1:
                flags.append("HISTORICAL_BUSINESS_CHANGE")
            if latest.get("waba_id") and len(
                waba_businesses[latest["waba_id"]]
            ) > 1:
                flags.append("WABA_CROSS_BUSINESS")
            if latest["evidence_kind"] not in DOCUMENT_KINDS:
                flags.append("OPERATOR_ONLY")
            if not latest.get("waba_id"):
                flags.append("WABA_NOT_RECORDED")
            state = (
                "DOCUMENTED_UNVERIFIED"
                if latest["evidence_kind"] in DOCUMENT_KINDS
                else "DECLARED_UNVERIFIED"
            )
        if default_counts[binding["sucursal_id"]] > 1:
            flags.append("MULTIPLE_DEFAULT_BRANCH")
        if any(flag in REVIEW_FLAGS for flag in flags):
            state = "REVIEW_REQUIRED"

        rows.append({
            "sucursal_id": int(binding["sucursal_id"]),
            "sucursal_canon": binding["sucursal_canon"],
            "provider_channel_id": channel,
            "business_id": latest.get("business_id") if latest and latest["state"] == "DECLARED" else None,
            "waba_id": latest.get("waba_id") if latest and latest["state"] == "DECLARED" else None,
            "evidence_kind": latest.get("evidence_kind") if latest and latest["state"] == "DECLARED" else None,
            "source_reference": latest.get("source_reference") if latest else None,
            "revision_id": int(latest["revision_id"]) if latest else None,
            "review_state": state,
            "flags": flags,
            "revision_count": len(history),
            "api_verified": False,
        })
    summary = Counter(row["review_state"] for row in rows)
    return {
        "rows": rows,
        "summary": {
            "total_channels": len(rows),
            "candidate_businesses": len(portfolio_ids),
            "pending": summary["PENDING"],
            "withdrawn": summary["WITHDRAWN"],
            "declared_unverified": summary["DECLARED_UNVERIFIED"],
            "documented_unverified": summary["DOCUMENTED_UNVERIFIED"],
            "review_required": summary["REVIEW_REQUIRED"],
            "api_verified": 0,
        },
        "basis": "OPERATOR_DOCUMENTARY_EVIDENCE_ONLY",
        "meta_verification_available": False,
    }


def list_portfolio_review(*, session=None) -> dict[str, Any]:
    """One GET, no writes. Fetch entire relevant history for accurate conflict flags."""
    active = session if session is not None else db.session
    bindings = list_channel_bindings(session=active, active_only=False)
    portfolio_rows = list_portfolio_references(session=active)["rows"]
    channels = {
        binding["provider_channel_id"] for binding in bindings
        if binding["provider"] == "IVENTAS"
        and binding["is_active"] and binding["is_default"]
    }
    revisions = []
    if channels:
        db_rows = active.query(Evidence).filter(
            Evidence.provider_channel_id.in_(sorted(channels)),
        ).order_by(Evidence.id.desc()).all()
        revisions = [
            {
                "revision_id": int(row.id),
                "provider_channel_id": row.provider_channel_id,
                "business_id": row.business_id,
                "waba_id": row.waba_id,
                "state": row.state,
                "evidence_kind": row.evidence_kind,
                "source_reference": row.source_reference,
            }
            for row in db_rows
        ]
    return build_portfolio_review(
        bindings=bindings, portfolios=portfolio_rows, revisions=revisions,
    )
