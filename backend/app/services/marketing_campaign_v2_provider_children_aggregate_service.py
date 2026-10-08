"""Pure, offline Campaign V2 provider-child analytics projection.

Only uses persisted provider children, snapshots and observations.  Provider
raw counts are *exposures*, not deduplicated people. No HTTP or writes.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Iterable, Mapping

from app.services.marketing_campaign_v2_reporting_cost_service import (
    extract_campaign_cost_projection,
)

_RAW_FIELDS = (
    "successful", "failed", "sent", "delivered", "viewed", "answered",
    "interaction_groups", "interaction_items",
)
_ACCEPTED = frozenset({"SUBMITTED", "SCHEDULED"})
_FAILURE = frozenset({"PROVIDER_ERROR", "FAILED", "BLOCKED"})


def build_campaign_v2_provider_children_aggregate(
    *,
    campaign_id: int,
    children: Iterable[Any],
    snapshots: Iterable[Any],
    observations: Iterable[Any] = (),
    cost_projector: Callable[[Any], Mapping[str, Any]] = extract_campaign_cost_projection,
) -> dict[str, Any]:
    """Aggregate latest evidence per provider child; never treat missing as zero."""
    ordered_children = sorted(children, key=lambda child: int(child.id))
    if any(int(child.campaign_v2_id) != int(campaign_id) for child in ordered_children):
        raise ValueError("Provider child fuera de la campaña solicitada.")
    if len({int(child.id) for child in ordered_children}) != len(ordered_children):
        raise ValueError("Provider child duplicado.")

    child_by_id = {int(child.id): child for child in ordered_children}
    child_ids = set(child_by_id)
    latest: dict[int, Any] = {}
    for snapshot in snapshots:
        if int(snapshot.campaign_v2_id) != int(campaign_id):
            continue
        linked = getattr(snapshot, "provider_campaign_child_id", None)
        if linked is not None:
            linked_id = int(linked)
            if linked_id not in child_ids:
                continue
            child = child_by_id[linked_id]
            if _identity(snapshot) != _identity(child):
                raise ValueError("Identidad provider incompatible entre child y snapshot.")
        else:
            identities = [
                int(child.id) for child in ordered_children
                if _identity(child) == _identity(snapshot)
                and _identity(child)[1] is not None
            ]
            if len(identities) != 1:
                continue
            linked_id = identities[0]
        existing = latest.get(linked_id)
        if existing is None or _sort_snapshot(snapshot) > _sort_snapshot(existing):
            latest[linked_id] = snapshot

    observations_by_snapshot: dict[int, list[Any]] = defaultdict(list)
    for observation in observations:
        observations_by_snapshot[int(observation.snapshot_id)].append(observation)

    result_children: list[dict[str, Any]] = []
    matched_unique: set[int] = set()
    recipient_states: dict[int, dict[str, Any]] = {}
    raw_totals = {key: 0 for key in _RAW_FIELDS}
    usable_stats_count = 0
    known_costs: list[tuple[str, Decimal]] = []
    for child in ordered_children:
        status = str(child.status)
        accepted = status in _ACCEPTED and bool(getattr(child, "provider_campaign_id", None))
        snapshot = latest.get(int(child.id)) if accepted else None
        analytics_status = getattr(snapshot, "analytics_status", None)
        usable = snapshot is not None and analytics_status == "ok"
        raw = (
            {field: int(getattr(snapshot, "raw_" + field)) for field in _RAW_FIELDS}
            if usable else None
        )
        if raw is not None:
            usable_stats_count += 1
            for field, value in raw.items():
                raw_totals[field] += value
            for row in observations_by_snapshot.get(int(snapshot.id), ()):
                recipient_id = getattr(row, "campaign_recipient_id", None)
                if recipient_id is None:
                    continue
                recipient_id = int(recipient_id)
                matched_unique.add(recipient_id)
                outcome = str(getattr(row, "outcome", "") or "").upper()
                delivery = str(getattr(row, "delivery_bucket", "") or "").upper()
                labels = getattr(row, "button_labels_json", None)
                state = recipient_states.setdefault(
                    recipient_id, {"successful": False, "failed": False,
                                   "delivery": None, "labels": set()}
                )
                if outcome == "SUCCESSFUL":
                    state["successful"] = True
                    if delivery in ("SENT", "DELIVERED", "VIEWED"):
                        old_rank = {"SENT": 1, "DELIVERED": 2, "VIEWED": 3}
                        if old_rank[delivery] > old_rank.get(state["delivery"], 0):
                            state["delivery"] = delivery
                elif outcome == "FAILED":
                    state["failed"] = True
                if isinstance(labels, list):
                    state["labels"].update(
                        label for label in labels
                        if isinstance(label, str) and label.strip()
                    )

        cost_projection = (
            cost_projector(snapshot.analytics_json)
            if usable else {"status": "unavailable", "currency": None, "total": None}
        )
        cost = _validated_cost(cost_projection)
        if cost is not None:
            known_costs.append(cost)
        result_children.append({
            "id": int(child.id),
            "sucursal_canon": getattr(child, "sucursal_canon", None),
            "provider": str(child.provider),
            "provider_campaign_id": getattr(child, "provider_campaign_id", None),
            "status": status,
            "recipient_count": int(child.recipient_count),
            "snapshot_id": int(snapshot.id) if snapshot is not None else None,
            "observed_at": (
                _sort_snapshot(snapshot)[0].isoformat() if snapshot is not None else None
            ),
            "analytics_status": analytics_status,
            "provider_raw": raw,
            "cost": dict(cost_projection),
        })

    accepted_count = sum(
        child["status"] in _ACCEPTED and bool(child["provider_campaign_id"])
        for child in result_children
    )
    pending_stats = len(ordered_children) - usable_stats_count
    normalized = {
        "successful": sum(state["successful"] for state in recipient_states.values()),
        "failed": sum(
            state["failed"] and not state["successful"]
            for state in recipient_states.values()
        ),
        "sent": sum(
            state["successful"] and state["delivery"] == "SENT"
            for state in recipient_states.values()
        ),
        "delivered": sum(
            state["successful"] and state["delivery"] == "DELIVERED"
            for state in recipient_states.values()
        ),
        "viewed": sum(
            state["successful"] and state["delivery"] == "VIEWED"
            for state in recipient_states.values()
        ),
        "reach_count": sum(
            state["successful"] and state["delivery"] in ("DELIVERED", "VIEWED")
            for state in recipient_states.values()
        ),
    }
    button_unique = sum(bool(state["labels"]) for state in recipient_states.values())
    cost = _aggregate_cost(
        known_costs=known_costs,
        child_count=len(ordered_children),
    )
    return {
        "campaign_id": int(campaign_id),
        "summary": {
            "status": _aggregate_status(result_children),
            "child_count": len(ordered_children),
            "accepted_batches": accepted_count,
            "scheduled_batches": sum(
                child["status"] == "SCHEDULED" for child in result_children
            ),
            "failed_batches": sum(
                child["status"] in _FAILURE for child in result_children
            ),
            "reconciliation_required_batches": sum(
                child["status"] == "RECONCILIATION_REQUIRED"
                for child in result_children
            ),
            "recipient_exposures_accepted": sum(
                child["recipient_count"] for child in result_children
                if child["status"] in _ACCEPTED
                and bool(child["provider_campaign_id"])
            ),
            "matched_frozen_recipients_unique": len(matched_unique),
            "normalized": normalized,
            "unique_button_recipients": button_unique,
            "unmatched_provider_count_observed": sum(
                int(getattr(latest[int(child.id)], "unmatched_provider_count", 0))
                for child in ordered_children
                if int(child.id) in latest and
                latest[int(child.id)].analytics_status == "ok" and
                child.status in _ACCEPTED
            ),
            "batches_with_usable_stats": usable_stats_count,
            "batches_without_usable_stats": pending_stats,
            "latest_observed_at": max(
                (child["observed_at"] for child in result_children
                 if child["observed_at"] is not None),
                default=None,
            ),
            "provider_raw": raw_totals if usable_stats_count else None,
            "provider_raw_status": (
                "unavailable" if not usable_stats_count else
                "complete" if pending_stats == 0 else "partial"
            ),
            "cost": cost,
        },
        "children": result_children,
        # Internal only: stripped before returning the public Reporting JSON.
        "_recipient_observations": [
            {
                "campaign_recipient_id": recipient_id,
                "outcome": "SUCCESSFUL" if state["successful"] else "FAILED",
                "delivery_bucket": state["delivery"] if state["successful"] else None,
                "button_labels_json": sorted(state["labels"]),
            }
            for recipient_id, state in sorted(recipient_states.items())
            if state["successful"] or state["failed"]
        ],
    }


def _identity(row: Any) -> tuple[str, str | None]:
    provider = str(row.provider).strip().upper()
    external = getattr(row, "provider_campaign_id", None)
    return provider, str(external).strip() if external else None


def _sort_snapshot(row: Any) -> tuple[datetime, int]:
    fetched = row.fetched_at
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return fetched.astimezone(timezone.utc), int(row.id)


def _validated_cost(projection: Mapping[str, Any]) -> tuple[str, Decimal] | None:
    if projection.get("status") not in ("complete", "available"):
        return None
    currency = projection.get("currency")
    total = projection.get("total")
    if not isinstance(currency, str) or not currency.strip():
        return None
    if total is None or isinstance(total, bool):
        return None
    try:
        amount = Decimal(str(total))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return currency.strip().upper(), amount


def _aggregate_cost(
    *, known_costs: list[tuple[str, Decimal]], child_count: int,
) -> dict[str, Any]:
    missing = child_count - len(known_costs)
    currencies = {currency for currency, _amount in known_costs}
    # Never sum unlike currencies or represent an unknown amount as zero.
    compatible = len(currencies) == 1
    return {
        "status": (
            "unavailable" if not known_costs or not compatible else
            "complete" if missing == 0 else "partial"
        ),
        "currency": next(iter(currencies)) if compatible else None,
        "total": (
            str(sum((amount for _, amount in known_costs), Decimal("0")))
            if compatible and missing == 0 and known_costs else None
        ),
        "known_total": (
            str(sum((amount for _, amount in known_costs), Decimal("0")))
            if compatible else None
        ),
        "known_children": len(known_costs),
        "missing_children": missing,
    }


def _aggregate_status(children: list[dict[str, Any]]) -> str:
    if not children:
        return "READY"
    statuses = [child["status"] for child in children]
    if "RECONCILIATION_REQUIRED" in statuses:
        return "RECONCILIATION_REQUIRED"
    accepted = [
        child for child in children
        if child["status"] in _ACCEPTED and child["provider_campaign_id"]
    ]
    if len(accepted) == len(children):
        if all(child["status"] == "SCHEDULED" for child in children):
            return "SCHEDULED"
        if all(child["status"] == "SUBMITTED" for child in children):
            return "SUBMITTED"
        return "PARTIALLY_SUBMITTED"
    if any(status in _FAILURE for status in statuses):
        return "PARTIALLY_FAILED" if accepted else "FAILED"
    if accepted:
        return "PARTIALLY_SUBMITTED"
    return "READY"


def load_campaign_v2_provider_children_aggregates(
    *, campaign_ids: Iterable[int], session,
) -> dict[int, dict[str, Any]]:
    """Bulk-read child analytics for pre-authorized campaigns, without HTTP.

    The caller must enforce user/branch visibility before passing campaign_ids.
    Returns only campaigns with provider children; legacy callers can keep
    their existing reporting projection for campaigns without child rows.
    """
    from sqlalchemy import func

    from app.models.marketing import (
        MarketingCampaignV2ProviderCampaignORM as Child,
        MarketingCampaignV2ProviderRecipientObservationORM as Observation,
        MarketingCampaignV2ProviderStatsSnapshotORM as Snapshot,
    )

    ids = sorted({int(value) for value in campaign_ids})
    if not ids:
        return {}

    with session.no_autoflush:
        children = (
            session.query(
                Child.id, Child.campaign_v2_id, Child.provider,
                Child.provider_campaign_id, Child.status,
                Child.recipient_count, Child.sucursal_canon,
            )
            .filter(Child.campaign_v2_id.in_(ids))
            .order_by(Child.campaign_v2_id, Child.id)
            .all()
        )
        if not children:
            return {}

        child_campaign_ids = sorted({int(child.campaign_v2_id) for child in children})
        ranked = (
            session.query(
                Snapshot.id.label("snapshot_id"),
                func.row_number().over(
                    partition_by=(
                        Snapshot.campaign_v2_id,
                        Snapshot.provider,
                        Snapshot.provider_campaign_id,
                    ),
                    order_by=(Snapshot.fetched_at.desc(), Snapshot.id.desc()),
                ).label("snapshot_rank"),
            )
            .filter(Snapshot.campaign_v2_id.in_(child_campaign_ids))
            .subquery()
        )
        snapshots = (
            session.query(Snapshot)
            .join(ranked, Snapshot.id == ranked.c.snapshot_id)
            .filter(ranked.c.snapshot_rank == 1)
            .all()
        )
        snapshot_ids = [int(item.id) for item in snapshots]
        observations = (
            session.query(
                Observation.snapshot_id,
                Observation.campaign_recipient_id,
                Observation.outcome,
                Observation.delivery_bucket,
                Observation.button_labels_json,
            )
            .filter(Observation.snapshot_id.in_(snapshot_ids))
            .all() if snapshot_ids else []
        )

    children_by_campaign: dict[int, list[Any]] = defaultdict(list)
    for child in children:
        children_by_campaign[int(child.campaign_v2_id)].append(child)
    snapshots_by_campaign: dict[int, list[Any]] = defaultdict(list)
    for snapshot in snapshots:
        snapshots_by_campaign[int(snapshot.campaign_v2_id)].append(snapshot)
    observations_by_snapshot: dict[int, list[Any]] = defaultdict(list)
    for observation in observations:
        observations_by_snapshot[int(observation.snapshot_id)].append(observation)

    return {
        campaign_id: build_campaign_v2_provider_children_aggregate(
            campaign_id=campaign_id,
            children=campaign_children,
            snapshots=snapshots_by_campaign.get(campaign_id, ()),
            observations=(
                item
                for snapshot in snapshots_by_campaign.get(campaign_id, ())
                for item in observations_by_snapshot.get(int(snapshot.id), ())
            ),
        )
        for campaign_id, campaign_children in children_by_campaign.items()
    }
