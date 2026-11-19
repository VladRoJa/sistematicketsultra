"""M2: deterministic cross-campaign attribution of *validated* sales to proven sends.

This pure, scheduler-side domain operation does NOT read Warehouse/iVentas, guess
delivery timestamps, charge the provider, or modify existing per-campaign reports.
The caller must first prove each SUCCESSFUL recipient within the submitted child
and obtain canonical, filtered Gasca membership transactions (order-level totals).
Never pass the returned transaction audit to a public endpoint without ACL review.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable


ATTRIBUTION_RULE_VERSION = "M2_LAST_PROVEN_SUBMISSION_V1"
_ALLOWED_KINDS = frozenset({"NUEVO", "REACTIVACION"})
_ALLOWED_WINDOWS = frozenset({7, 14, 30})


class UniqueSalesEvidenceError(ValueError):
    """Unverifiable/mismatched source evidence; do not silently count revenue."""


@dataclass(frozen=True)
class ProvenContact:
    campaign_id: int
    child_id: int
    provider_campaign_id: str
    branch_id: int
    phone_mx10: str
    sale_kind: str
    submitted_at: datetime


@dataclass(frozen=True)
class CanonicalMembershipTransaction:
    """A fully validated, positive net transaction (all eligible order rows added).

    transaction_key must be stable across cumulative canonical snapshots. Filtering
    by membership product, Gasca status, sale kind, refunds and branch aliases
    happens upstream; these are never inferred from a phone alone.
    """

    transaction_key: str
    branch_id: int
    phone_mx10: str
    sale_kind: str
    occurred_at: datetime
    amount_mxn: Decimal
    venta_total_snapshot_id: int


def _utc(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise UniqueSalesEvidenceError(f"{label} debe contener zona horaria.")
    return value.astimezone(timezone.utc)


def _valid_phone(phone: str) -> bool:
    return isinstance(phone, str) and len(phone) == 10 and phone.isascii() and phone.isdigit()


def _positive_id(value: int) -> bool:
    return type(value) is int and value > 0


def _check_identity(*, phone: str, branch_id: int, sale_kind: str) -> None:
    if not _valid_phone(phone) or not _positive_id(branch_id) or sale_kind not in _ALLOWED_KINDS:
        raise UniqueSalesEvidenceError("Teléfono, sucursal o clase de venta no verificables.")


def _check_contact(entry: ProvenContact) -> None:
    if not isinstance(entry, ProvenContact):
        raise UniqueSalesEvidenceError("La evidencia de contacto es inválida.")
    _check_identity(phone=entry.phone_mx10, branch_id=entry.branch_id, sale_kind=entry.sale_kind)
    if not _positive_id(entry.campaign_id) or not _positive_id(entry.child_id):
        raise UniqueSalesEvidenceError("Identidad de campaña/child inválida.")
    if not isinstance(entry.provider_campaign_id, str) or not entry.provider_campaign_id.strip():
        raise UniqueSalesEvidenceError("Falta identidad provider del child enviado.")
    _utc(entry.submitted_at, "submitted_at")


def _check_transaction(entry: CanonicalMembershipTransaction) -> None:
    if not isinstance(entry, CanonicalMembershipTransaction):
        raise UniqueSalesEvidenceError("La evidencia de venta es inválida.")
    _check_identity(phone=entry.phone_mx10, branch_id=entry.branch_id, sale_kind=entry.sale_kind)
    if not isinstance(entry.transaction_key, str) or not entry.transaction_key.strip():
        raise UniqueSalesEvidenceError("Falta identidad estable de transacción.")
    if not _positive_id(entry.venta_total_snapshot_id):
        raise UniqueSalesEvidenceError("La venta no referencia snapshot canónico.")
    _utc(entry.occurred_at, "ocurrió la venta")
    try:
        amount = Decimal(str(entry.amount_mxn))
    except (TypeError, ValueError, InvalidOperation) as exc:
        raise UniqueSalesEvidenceError("Importe de venta inválido.") from exc
    if not amount.is_finite() or amount <= 0 or amount != amount.quantize(Decimal("0.01")):
        raise UniqueSalesEvidenceError("La venta debe tener importe neto positivo MXN.")


def _sale_identity(sale: CanonicalMembershipTransaction) -> tuple[int, str, str, str]:
    return (sale.branch_id, sale.phone_mx10, sale.sale_kind, sale.transaction_key.strip())


def allocate_unique_membership_sales(
    *,
    contacts: Iterable[ProvenContact],
    transactions: Iterable[CanonicalMembershipTransaction],
    window_days: int,
) -> dict:
    """Attribute each canonical sale to one last eligible previous submission.

    Outputs only aggregate counts by campaign and a no-phone transaction audit
    intended for the scheduler; it makes no causal lift or final billing claim.
    """
    if type(window_days) is not int or window_days not in _ALLOWED_WINDOWS:
        raise UniqueSalesEvidenceError("Ventana comercial debe ser 7, 14 o 30 días.")

    by_identity: dict[tuple[str, int, str], list[ProvenContact]] = defaultdict(list)
    proof_keys: set[tuple[int, int, str, str, int, str, datetime]] = set()
    campaign_ids: set[int] = set()
    for contact in contacts:
        _check_contact(contact)
        campaign_ids.add(contact.campaign_id)
        when = _utc(contact.submitted_at, "submitted_at")
        proof = (contact.campaign_id, contact.child_id, contact.provider_campaign_id,
                 contact.phone_mx10, contact.branch_id, contact.sale_kind, when)
        if proof in proof_keys:
            continue
        proof_keys.add(proof)
        by_identity[(contact.phone_mx10, contact.branch_id, contact.sale_kind)].append(contact)

    for entries in by_identity.values():
        entries.sort(key=lambda c: (
            _utc(c.submitted_at, "submitted_at"),
            c.child_id,
            c.campaign_id,
            c.provider_campaign_id,
        ), reverse=True)

    unique_sales: dict[tuple[int, str, str, str], CanonicalMembershipTransaction] = {}
    duplicates = 0
    for sale in transactions:
        _check_transaction(sale)
        key = _sale_identity(sale)
        old = unique_sales.get(key)
        if old is not None:
            if (_utc(old.occurred_at, "occurred_at") != _utc(sale.occurred_at, "occurred_at")
                    or Decimal(str(old.amount_mxn)) != Decimal(str(sale.amount_mxn))):
                raise UniqueSalesEvidenceError(
                    "Una transacción aparece con importe/fecha diferentes; falta reconciliar los cortes."
                )
            duplicates += 1
            # Prefer the latest proven canonical cut, never add cumulative snapshots.
            if sale.venta_total_snapshot_id > old.venta_total_snapshot_id:
                unique_sales[key] = sale
            continue
        unique_sales[key] = sale

    allocated = defaultdict(lambda: {"transactions": 0, "revenue": Decimal("0"),
                                     "buyers": set(), "assists": 0})
    allocations = []
    unmatched = 0
    for key, sale in sorted(unique_sales.items(), key=lambda item: item[0]):
        occurred = _utc(sale.occurred_at, "ocurrió la venta")
        choices = [
            candidate for candidate in by_identity.get(
                (sale.phone_mx10, sale.branch_id, sale.sale_kind), ()
            )
            if timedelta(0) < occurred - _utc(candidate.submitted_at, "submitted_at")
            <= timedelta(days=window_days)
        ]
        if not choices:
            unmatched += 1
            continue
        primary = choices[0]
        assists = sorted({candidate.campaign_id for candidate in choices[1:]
                          if candidate.campaign_id != primary.campaign_id})
        metrics = allocated[primary.campaign_id]
        metrics["transactions"] += 1
        metrics["revenue"] += Decimal(str(sale.amount_mxn))
        metrics["buyers"].add(sale.phone_mx10)
        for assisted_campaign in assists:
            allocated[assisted_campaign]["assists"] += 1
        allocations.append({
            "transaction_ref": sale.transaction_key.strip(),
            "venta_total_snapshot_id": sale.venta_total_snapshot_id,
            "campaign_id": primary.campaign_id,
            "child_id": primary.child_id,
            "provider_campaign_id": primary.provider_campaign_id,
            "assisted_campaign_ids": assists,
        })

    campaigns = []
    for campaign_id in sorted(campaign_ids):
        data = allocated[campaign_id]
        campaigns.append({
            "campaign_id": campaign_id,
            "buyers_observed": len(data["buyers"]),
            "transactions_observed": data["transactions"],
            "revenue_observed_mxn": format(data["revenue"].quantize(Decimal("0.01")), ".2f"),
            "assisted_transactions": data["assists"],
        })
    revenue = sum((data["revenue"] for data in allocated.values()), Decimal("0"))
    return {
        "rule_version": ATTRIBUTION_RULE_VERSION,
        "status": "EVIDENCE_PREVALIDATED",
        "window_days": window_days,
        "transactions_seen": len(unique_sales),
        "duplicate_transaction_rows_ignored": duplicates,
        "transactions_observed": len(allocations),
        "transactions_unmatched": unmatched,
        "revenue_observed_mxn": format(revenue.quantize(Decimal("0.01")), ".2f"),
        "campaigns": campaigns,
        "allocations_private": allocations,
        "limitations": [
            "La venta es posterior al ENVÍO probado, no a la hora individual de recepción.",
            "Relación temporal observada: NO demuestra causalidad incremental.",
            "No incluye costos reales ni calcula ROAS hasta conciliación de monedas.",
        ],
    }
