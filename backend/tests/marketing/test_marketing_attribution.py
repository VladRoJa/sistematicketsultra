from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.services.marketing_attribution import (
    SaleRecord,
    VisitEvent,
    count_unique_visitors,
    reconcile_visit_sales,
    safe_divide,
)


PHONE_A = "0000000000"
PHONE_B = "1111111111"


def _visit(
    *,
    event_key: str = "visit-1",
    branch_id: int = 1,
    visit_date: date = date(2026, 7, 1),
    phone: str = PHONE_A,
) -> VisitEvent:
    return VisitEvent(
        event_key=event_key,
        branch_id=branch_id,
        visit_date=visit_date,
        phone=phone,
        description="PASE 2 DIAS GRATIS",
    )


def _sale(
    *,
    sale_key: str = "sale-1",
    branch_id: int = 1,
    payment_date: date = date(2026, 7, 1),
    phone: str = PHONE_A,
    member_id: str | None = "member-1",
) -> SaleRecord:
    return SaleRecord(
        sale_key=sale_key,
        branch_id=branch_id,
        payment_date=payment_date,
        phone=phone,
        member_id=member_id,
        revenue=Decimal("100.00"),
    )


def test_sale_on_visit_date_is_attributed():
    result = reconcile_visit_sales(
        visits=[_visit()],
        sales=[_sale()],
    )

    assert len(result) == 1


def test_sale_exactly_thirty_days_after_visit_is_attributed():
    result = reconcile_visit_sales(
        visits=[_visit()],
        sales=[
            _sale(
                payment_date=date(2026, 7, 1)
                + timedelta(days=30)
            )
        ],
    )

    assert len(result) == 1


def test_sale_thirty_one_days_after_visit_is_not_attributed():
    result = reconcile_visit_sales(
        visits=[_visit()],
        sales=[
            _sale(
                payment_date=date(2026, 7, 1)
                + timedelta(days=31)
            )
        ],
    )

    assert result == []


def test_sale_before_visit_is_not_attributed():
    result = reconcile_visit_sales(
        visits=[_visit(visit_date=date(2026, 7, 2))],
        sales=[_sale(payment_date=date(2026, 7, 1))],
    )

    assert result == []


def test_same_phone_in_different_branch_is_not_attributed():
    result = reconcile_visit_sales(
        visits=[_visit(branch_id=1)],
        sales=[_sale(branch_id=2)],
    )

    assert result == []


def test_nearest_previous_visit_is_selected():
    older = _visit(
        event_key="visit-old",
        visit_date=date(2026, 7, 1),
    )
    nearest = _visit(
        event_key="visit-nearest",
        visit_date=date(2026, 7, 9),
    )

    result = reconcile_visit_sales(
        visits=[older, nearest],
        sales=[_sale(payment_date=date(2026, 7, 10))],
    )

    assert result[0].visit == nearest


def test_duplicate_member_sale_is_counted_once():
    result = reconcile_visit_sales(
        visits=[_visit()],
        sales=[
            _sale(
                sale_key="sale-first",
                payment_date=date(2026, 7, 2),
            ),
            _sale(
                sale_key="sale-duplicate",
                payment_date=date(2026, 7, 3),
            ),
        ],
    )

    assert len(result) == 1
    assert result[0].sale.sale_key == "sale-first"


def test_unique_visitors_use_branch_and_normalized_phone():
    assert (
        count_unique_visitors(
            [
                _visit(event_key="visit-1"),
                _visit(event_key="visit-2"),
                _visit(
                    event_key="visit-3",
                    phone=PHONE_B,
                ),
                _visit(
                    event_key="visit-4",
                    branch_id=2,
                ),
            ]
        )
        == 3
    )


def test_safe_divide_returns_none_for_zero_denominator():
    assert safe_divide(Decimal("100.00"), 0) is None
