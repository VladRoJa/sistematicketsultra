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

    observations_by_snapshot: dict[int, set[int]] = defaultdict(set)
    for observation in observations:
        recipient_id = getattr(observation, "campaign_recipient_id", None)
        if recipient_id is not None:
            observations_by_snapshot[int(observation.snapshot_id)].add(int(recipient_id))

    result_children: list[dict[str, Any]] = []
    matched_unique: set[int] = set()
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
            matched_unique.update(
                observations_by_snapshot.get(int(snapshot.id), set())
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
            "analytics_status": analytics_status,
            "provider_raw": raw,
            "cost": dict(cost_projection),
        })

    accepted_count = sum(
        child["status"] in _ACCEPTED and bool(child["provider_campaign_id"])
        for child in result_children
    )
    pending_stats = len(ordered_children) - usable_stats_count
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
            "batches_with_usable_stats": usable_stats_count,
            "batches_without_usable_stats": pending_stats,
            "provider_raw": raw_totals if usable_stats_count else None,
            "provider_raw_status": (
                "unavailable" if not usable_stats_count else
                "complete" if pending_stats == 0 else "partial"
            ),
            "cost": cost,
        },
        "children": result_children,
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
