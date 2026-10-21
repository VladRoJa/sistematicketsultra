"""Pure, auditable historical Meta spend allocation by city.

This module has no database access and is NOT connected to the live Funnel.
The caller must prove that each branch operated in the source month and that
the Meta ad-set amount belongs to exactly one city before passing branch IDs.

Only spend is allocated. No leads, conversations, visits, sales or revenue are
inferred or divided here. Do not pass an entire multi-city campaign as source.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable


CENT = Decimal("0.01")
ESTIMATED_CITY_SPLIT = "ESTIMATED_CITY_SPLIT"
# Administrative entries in sucursales are never eligible gym branches.
RESERVED_NON_GYM_BRANCH_IDS = frozenset({100, 1000})
_PERIOD_KEY_PATTERN = re.compile(r"META-\d{4}-\d{2}")


@dataclass(frozen=True)
class HistoricalMetaAdsetSource:
    """One Meta ad set, for one observed month and verified city."""

    period_key: str
    account_id: str
    campaign_id: str
    adset_id: str
    city_key: str


@dataclass(frozen=True)
class HistoricalMetaSpendAllocation:
    """Estimated monthly spend for one eligible gym branch."""

    source: HistoricalMetaAdsetSource
    sucursal_id: int
    spend: Decimal
    allocation_method: str = ESTIMATED_CITY_SPLIT


def _validate_source(source: HistoricalMetaAdsetSource) -> None:
    if not isinstance(source, HistoricalMetaAdsetSource):
        raise TypeError("source debe ser HistoricalMetaAdsetSource.")
    if not _PERIOD_KEY_PATTERN.fullmatch(source.period_key):
        raise ValueError("period_key debe tener formato META-YYYY-MM.")
    try:
        date.fromisoformat(source.period_key[5:] + "-01")
    except ValueError as exc:
        raise ValueError("period_key contiene un mes inválido.") from exc
    for field_name in ("account_id", "campaign_id", "adset_id", "city_key"):
        value = getattr(source, field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} debe ser texto no vacío.")


def allocate_historical_city_spend(
    *,
    source: HistoricalMetaAdsetSource,
    spend: Decimal,
    eligible_branch_ids: Iterable[int],
) -> tuple[HistoricalMetaSpendAllocation, ...]:
    """Split one city's ad-set spend equally across proven operating gyms.

    Accepts only exact cent amounts; a fractional cent is never silently lost.
    Orders by canonical sucursal_id for stable remainder-cent assignment.
    Rejects administrative/duplicate branch IDs instead of quietly adjusting
    the denominator. Responsibility for month-specific eligibility belongs to
    the separate historical branch resolver, not to this math-only module.
    """
    _validate_source(source)
    if not isinstance(spend, Decimal):
        raise TypeError("spend debe ser Decimal, nunca float.")
    if not spend.is_finite() or spend < 0:
        raise ValueError("spend debe ser finito y no negativo.")
    if spend != spend.quantize(CENT):
        raise ValueError("spend tiene fracciones de centavo; revisar origen.")

    branches = tuple(eligible_branch_ids)
    if not branches:
        raise ValueError("No hay sucursales elegibles verificadas.")
    if any(type(branch_id) is not int or branch_id <= 0 for branch_id in branches):
        raise ValueError("Los sucursal_id deben ser enteros positivos.")
    if len(branches) != len(set(branches)):
        raise ValueError("Sucursales duplicadas en el reparto.")
    if RESERVED_NON_GYM_BRANCH_IDS.intersection(branches):
        raise ValueError("No se permite asignar gasto a unidades administrativas.")

    ordered = sorted(branches)
    total_cents = int(spend / CENT)
    base_cents, remaining_cents = divmod(total_cents, len(ordered))
    allocations = tuple(
        HistoricalMetaSpendAllocation(
            source=source,
            sucursal_id=branch_id,
            spend=Decimal(base_cents + (index < remaining_cents)) * CENT,
        )
        for index, branch_id in enumerate(ordered)
    )
    if sum((row.spend for row in allocations), Decimal("0")) != spend:
        raise RuntimeError("El reparto histórico no concilia con Meta.")
    return allocations
