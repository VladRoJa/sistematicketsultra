from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable


ATTRIBUTION_WINDOW_DAYS = 30


@dataclass(frozen=True)
class VisitEvent:
    event_key: str
    branch_id: int
    visit_date: date
    phone: str
    description: str


@dataclass(frozen=True)
class SaleRecord:
    sale_key: str
    branch_id: int
    payment_date: date
    phone: str
    member_id: str | None
    revenue: Decimal
    snapshot_id: int | None = None
    source_row_id: int | None = None
    folio: str | None = None
    member_name: str | None = None
    membership_type: str | None = None
    tariff: str | None = None
    registration: str | None = None
    pass_name: str | None = None
    payment_place: str | None = None
    listed_total: Decimal | None = None


@dataclass(frozen=True)
class AttributedSale:
    sale: SaleRecord
    visit: VisitEvent


def deduplicate_visit_events(
    events: Iterable[VisitEvent],
) -> list[VisitEvent]:
    unique_by_key: dict[str, VisitEvent] = {}

    for event in sorted(
        events,
        key=lambda item: (
            item.visit_date,
            item.branch_id,
            item.phone,
            item.event_key,
        ),
    ):
        unique_by_key.setdefault(event.event_key, event)

    return list(unique_by_key.values())


def deduplicate_sales(
    sales: Iterable[SaleRecord],
) -> list[SaleRecord]:
    unique_by_key: dict[str, SaleRecord] = {}

    for sale in sorted(
        sales,
        key=lambda item: (
            item.payment_date,
            item.member_id or "",
            item.sale_key,
        ),
    ):
        dedupe_key = sale.member_id or sale.sale_key
        unique_by_key.setdefault(dedupe_key, sale)

    return list(unique_by_key.values())


def reconcile_visit_sales(
    *,
    visits: Iterable[VisitEvent],
    sales: Iterable[SaleRecord],
) -> list[AttributedSale]:
    visits_by_identity: dict[
        tuple[int, str],
        list[VisitEvent],
    ] = defaultdict(list)

    for visit in deduplicate_visit_events(visits):
        visits_by_identity[
            (visit.branch_id, visit.phone)
        ].append(visit)

    for identity_visits in visits_by_identity.values():
        identity_visits.sort(
            key=lambda item: (
                item.visit_date,
                item.event_key,
            )
        )

    attributed: list[AttributedSale] = []

    for sale in deduplicate_sales(sales):
        candidates = [
            visit
            for visit in visits_by_identity.get(
                (sale.branch_id, sale.phone),
                [],
            )
            if visit.visit_date <= sale.payment_date
            and sale.payment_date
            <= visit.visit_date
            + timedelta(days=ATTRIBUTION_WINDOW_DAYS)
        ]

        if not candidates:
            continue

        selected_visit = max(
            candidates,
            key=lambda item: (
                item.visit_date,
                item.event_key,
            ),
        )
        attributed.append(
            AttributedSale(
                sale=sale,
                visit=selected_visit,
            )
        )

    return attributed


def count_unique_visitors(
    events: Iterable[VisitEvent],
) -> int:
    return len(
        {
            (event.branch_id, event.phone)
            for event in events
        }
    )


def safe_divide(
    numerator: Decimal | int,
    denominator: Decimal | int,
) -> Decimal | None:
    normalized_denominator = Decimal(str(denominator))
    if normalized_denominator == 0:
        return None

    return Decimal(str(numerator)) / normalized_denominator
