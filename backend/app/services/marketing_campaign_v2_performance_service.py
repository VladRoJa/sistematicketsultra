"""M1: read-only effectiveness of real Campaign V2 iVentas submissions.

The period is the *submission* month in America/Tijuana, not snapshot time.
Only the latest provider snapshot per child is used. No provider HTTP or writes.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, func

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2ProviderCampaignORM,
    MarketingCampaignV2ProviderRecipientObservationORM,
    MarketingCampaignV2ProviderStatsSnapshotORM,
)
from app.services.marketing_campaign_v2_query_service import (
    _campaign_visible_to_scope,
    _normalize_current_scope,
)
from app.services.marketing_campaign_v2_usd_pricing_service import (
    USD_PER_DELIVERED,
    USD_RATE_VERSION,
)
from app.warehouse.services.socios_vencidos_current_status_resolver import (
    normalize_socios_vencidos_branch_key,
)


_TZ = ZoneInfo("America/Tijuana")


class CampaignV2PerformanceValidationError(ValueError):
    """Invalid request window for the M1 dashboard."""


def _window(from_date: str, to_date: str) -> tuple[date, date, datetime, datetime]:
    if not isinstance(from_date, str) or not isinstance(to_date, str):
        raise CampaignV2PerformanceValidationError("Indica fecha inicial y final YYYY-MM-DD.")
    try:
        start = date.fromisoformat(from_date)
        end = date.fromisoformat(to_date)
    except ValueError as exc:
        raise CampaignV2PerformanceValidationError("Las fechas deben ser YYYY-MM-DD.") from exc
    if start.isoformat() != from_date or end.isoformat() != to_date:
        raise CampaignV2PerformanceValidationError("Las fechas deben ser YYYY-MM-DD.")
    if end < start or (end - start).days >= 31:
        raise CampaignV2PerformanceValidationError("El rango debe ser de 1 a 31 días inclusivos.")
    start_utc = datetime.combine(start, time.min, _TZ).astimezone(timezone.utc)
    end_utc = datetime.combine(end + timedelta(days=1), time.min, _TZ).astimezone(timezone.utc)
    return start, end, start_utc, end_utc


def _frequency_buckets(once: int, twice: int, thrice: int, four_plus: int) -> dict:
    return {"once": once, "twice": twice, "three": thrice, "four_plus": four_plus}


def _summarize_lots(lots: list[dict]) -> dict:
    """Pure M1 arithmetic; incomplete evidence is never a zero-priced invoice."""
    keys = ("recipient_count", "successful", "failed", "sent", "delivered", "viewed")
    totals = {key: sum(int(lot[key]) for lot in lots if lot["has_snapshot"])
              for key in keys if key != "recipient_count"}
    totals["recipient_count"] = sum(int(lot["recipient_count"]) for lot in lots)
    totals["lots"] = len(lots)
    totals["lots_with_snapshot"] = sum(bool(lot["has_snapshot"]) for lot in lots)
    totals["lots_without_snapshot"] = totals["lots"] - totals["lots_with_snapshot"]
    totals["lots_with_recipient_mismatch"] = sum(
        bool(lot["recipient_mismatch"]) for lot in lots if lot["has_snapshot"]
    )
    # USD reference is not actual provider billing; SUCCESSFUL includes SENT.
    billable_proxy = totals["delivered"] + totals["viewed"]
    estimate = Decimal(billable_proxy) * USD_PER_DELIVERED
    totals["estimated_delivered_usd"] = format(estimate.quantize(Decimal("0.0001")), ".4f")
    totals["estimated_delivery_count"] = billable_proxy
    totals["evidence_status"] = (
        "INCOMPLETE" if totals["lots_without_snapshot"] or totals["lots_with_recipient_mismatch"]
        else "COMPLETE"
    )
    return totals


def build_campaign_v2_performance(
    *, from_date: str, to_date: str, allowed_sucursal_keys, session=None,
) -> dict:
    """Scope-isolated aggregate; never returns phones or raw provider payloads."""
    start, end, start_utc, end_utc = _window(from_date, to_date)
    scope = _normalize_current_scope(allowed_sucursal_keys)
    active = session if session is not None else db.session
    Child = MarketingCampaignV2ProviderCampaignORM
    Campaign = MarketingCampaignV2ORM
    Snapshot = MarketingCampaignV2ProviderStatsSnapshotORM
    Obs = MarketingCampaignV2ProviderRecipientObservationORM

    with active.no_autoflush:
        rows = (
            active.query(Child, Campaign)
            .join(Campaign, Campaign.id == Child.campaign_v2_id)
            .filter(
                Child.provider == "IVENTAS",
                Child.status == "SUBMITTED",
                Child.provider_campaign_id.isnot(None),
                Child.submitted_at >= start_utc,
                Child.submitted_at < end_utc,
            ).all()
        )
        selected = []
        visible_names = {}
        for child, campaign in rows:
            branch = normalize_socios_vencidos_branch_key(child.sucursal_canon)
            if (branch and _campaign_visible_to_scope(campaign, scope)
                    and (scope is None or branch in scope)):
                selected.append((child, branch))
                visible_names[int(campaign.id)] = str(campaign.name)
        selected.sort(key=lambda entry: (entry[1], int(entry[0].id)))
        campaign_ids = sorted({int(child.campaign_v2_id) for child, _ in selected})
        latest_by_identity = {}
        if campaign_ids:
            ranked = (
                active.query(
                    Snapshot.id.label("snapshot_id"),
                    func.row_number().over(
                        partition_by=(Snapshot.campaign_v2_id, Snapshot.provider,
                                      Snapshot.provider_campaign_id),
                        order_by=(Snapshot.fetched_at.desc(), Snapshot.id.desc()),
                    ).label("snapshot_rank"),
                )
                .filter(Snapshot.provider == "IVENTAS",
                        Snapshot.campaign_v2_id.in_(campaign_ids))
                .subquery()
            )
            snapshots = (
                active.query(Snapshot).join(
                    ranked, Snapshot.id == ranked.c.snapshot_id
                ).filter(ranked.c.snapshot_rank == 1).all()
            )
            latest_by_identity = {
                (int(s.campaign_v2_id), str(s.provider_campaign_id)): s
                for s in snapshots
            }

        selected_ids = [int(c.id) for c, _ in selected]
        snapshot_to_child = {}
        snapshot_by_child = {}
        lots = []
        lots_by_branch = defaultdict(list)
        lots_by_campaign = defaultdict(list)
        for child, branch in selected:
            snapshot = latest_by_identity.get(
                (int(child.campaign_v2_id), str(child.provider_campaign_id))
            )
            # Defend against reused provider identities: ambiguous observations
            # must never be counted twice in the same period.
            lot = {
                "child_id": int(child.id),
                "branch": branch,
                "recipient_count": int(child.recipient_count),
                "has_snapshot": snapshot is not None,
                "recipient_mismatch": False,
                **{
                    key: int(getattr(snapshot, "raw_" + key)) if snapshot else 0
                    for key in ("successful", "failed", "sent", "delivered", "viewed")
                },
            }
            if snapshot is not None:
                sid = int(snapshot.id)
                if sid in snapshot_to_child:
                    # Same source ID in several children is not disjoint proof.
                    raise CampaignV2PerformanceValidationError(
                        "Existe una identidad provider duplicada entre lotes; requiere conciliación."
                    )
                snapshot_to_child[sid] = int(child.id)
                snapshot_by_child[int(child.id)] = sid
            lots.append(lot)
            lots_by_branch[branch].append(lot)
            lots_by_campaign[int(child.campaign_v2_id)].append(lot)

        snapshot_ids = sorted(snapshot_to_child)
        if snapshot_ids:
            observed = (
                active.query(
                    Obs.snapshot_id,
                    func.count().filter(Obs.outcome == "SUCCESSFUL").label("success_count"),
                    func.count().filter(Obs.outcome == "FAILED").label("failed_count"),
                ).filter(Obs.snapshot_id.in_(snapshot_ids))
                .group_by(Obs.snapshot_id).all()
            )
            counts = {
                int(row.snapshot_id): (int(row.success_count), int(row.failed_count))
                for row in observed
            }
            for lot in lots:
                if not lot["has_snapshot"]:
                    continue
                observed_success, observed_failed = counts.get(
                    snapshot_by_child[lot["child_id"]], (0, 0)
                )
                lot["recipient_mismatch"] = (
                    observed_success != lot["successful"] or observed_failed != lot["failed"]
                )
        summary = _summarize_lots(lots)

        # Database does phone aggregation; avoid transferring hundreds of
        # thousands of personal identifiers to the Python worker or browser.
        frequency = _frequency_buckets(0, 0, 0, 0)
        distinct_phones = 0
        repeated_phones = 0
        distinct_by_branch = {}
        distinct_by_campaign = {}
        if snapshot_ids:
            phone_counts = (
                active.query(
                    Obs.normalized_phone.label("phone"),
                    func.count(Obs.id).label("frequency"),
                ).filter(Obs.snapshot_id.in_(snapshot_ids),
                         Obs.outcome == "SUCCESSFUL")
                .group_by(Obs.normalized_phone).subquery()
            )
            freq_row = active.query(
                func.count().label("unique"),
                func.sum(case((phone_counts.c.frequency == 1, 1), else_=0)).label("once"),
                func.sum(case((phone_counts.c.frequency == 2, 1), else_=0)).label("twice"),
                func.sum(case((phone_counts.c.frequency == 3, 1), else_=0)).label("thrice"),
                func.sum(case((phone_counts.c.frequency >= 4, 1), else_=0)).label("four_plus"),
            ).one()
            distinct_phones = int(freq_row.unique or 0)
            frequency = _frequency_buckets(
                int(freq_row.once or 0), int(freq_row.twice or 0),
                int(freq_row.thrice or 0), int(freq_row.four_plus or 0),
            )
            repeated_phones = distinct_phones - frequency["once"]

            per_branch_phone = (
                active.query(
                    Child.sucursal_canon.label("branch"),
                    Obs.normalized_phone.label("phone"),
                    func.count(Obs.id).label("frequency"),
                ).select_from(Obs)
                .join(Snapshot, Snapshot.id == Obs.snapshot_id)
                .join(Child, and_(
                    Child.campaign_v2_id == Snapshot.campaign_v2_id,
                    Child.provider == Snapshot.provider,
                    Child.provider_campaign_id == Snapshot.provider_campaign_id,
                ))
                .filter(
                    Obs.snapshot_id.in_(snapshot_ids),
                    Child.id.in_(selected_ids),
                    Obs.outcome == "SUCCESSFUL",
                ).group_by(Child.sucursal_canon, Obs.normalized_phone).subquery()
            )
            branch_rows = active.query(
                per_branch_phone.c.branch,
                func.count().label("unique"),
                func.sum(case((per_branch_phone.c.frequency >= 2, 1), else_=0)).label("repeated"),
            ).group_by(per_branch_phone.c.branch).all()
            distinct_by_branch = {
                normalize_socios_vencidos_branch_key(row.branch): (
                    int(row.unique), int(row.repeated or 0)
                ) for row in branch_rows
            }

            per_campaign_phone = (
                active.query(
                    Child.campaign_v2_id.label("campaign_id"),
                    Obs.normalized_phone.label("phone"),
                    func.count(Obs.id).label("frequency"),
                ).select_from(Obs)
                .join(Snapshot, Snapshot.id == Obs.snapshot_id)
                .join(Child, and_(
                    Child.campaign_v2_id == Snapshot.campaign_v2_id,
                    Child.provider == Snapshot.provider,
                    Child.provider_campaign_id == Snapshot.provider_campaign_id,
                ))
                .filter(
                    Obs.snapshot_id.in_(snapshot_ids),
                    Child.id.in_(selected_ids),
                    Obs.outcome == "SUCCESSFUL",
                ).group_by(Child.campaign_v2_id, Obs.normalized_phone).subquery()
            )
            campaign_rows = active.query(
                per_campaign_phone.c.campaign_id,
                func.count().label("unique"),
                func.sum(case((per_campaign_phone.c.frequency >= 2, 1), else_=0)).label("repeated"),
            ).group_by(per_campaign_phone.c.campaign_id).all()
            distinct_by_campaign = {
                int(row.campaign_id): (int(row.unique), int(row.repeated or 0))
                for row in campaign_rows
            }

    campaigns = []
    for campaign_id in sorted(lots_by_campaign):
        item = _summarize_lots(lots_by_campaign[campaign_id])
        item["campaign_id"] = campaign_id
        item["name"] = visible_names[campaign_id]
        item["unique_successful_phones"], item["repeated_successful_phones"] = (
            distinct_by_campaign.get(campaign_id, (0, 0))
        )
        campaigns.append(item)

    branches = []
    for branch in sorted(lots_by_branch):
        item = _summarize_lots(lots_by_branch[branch])
        item["sucursal_canon"] = branch
        item["unique_successful_phones"], item["repeated_successful_phones"] = (
            distinct_by_branch.get(branch, (0, 0))
        )
        branches.append(item)

    return {
        "period": {"from": start.isoformat(), "to": end.isoformat(),
                   "timezone": "America/Tijuana", "basis": "SUBMITTED_AT"},
        "source": "SUITE_V2_IVENTAS_SUBMITTED_CHILDREN",
        "campaign_count": len(campaign_ids),
        "summary": {
            **summary,
            "unique_successful_phones": distinct_phones,
            "repeated_successful_phones": repeated_phones,
        },
        "frequency": frequency,
        "campaigns": campaigns,
        "branches": branches,
        "cost": {
            "currency": "USD",
            "status": "INDICATIVE_ONLY",
            "unit_cost_usd": format(USD_PER_DELIVERED, ".4f"),
            "rate_version": USD_RATE_VERSION,
            "estimated_delivered_usd": summary["estimated_delivered_usd"],
            "actual_billed_usd": None,
            "basis": "RAW_DELIVERED_PLUS_RAW_VIEWED_X_REFERENCE_RATE_NOT_PROVIDER_BILLING",
        },
        "caveats": [
            "SUCCESSFUL no equivale necesariamente a mensaje facturable.",
            "Sin snapshot se desconoce la entrega; no se imputa cero real.",
            "No incluye envíos hechos directamente en el panel iVentas.",
            "Frecuencia se mide entre éxitos observados, no intentos ni personas físicas.",
        ],
    }
