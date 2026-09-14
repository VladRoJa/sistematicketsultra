from datetime import date
from decimal import Decimal

from app.services.marketing_attribution import SaleRecord
from app.services.marketing_sales_funnel_service import (
    ORIGIN_IVENTAS_META,
)
from app.services.marketing_visit_conversion_service import (
    VisitConversionRow,
    _metric_matches,
    _serialize_metrics,
)


def _sale() -> SaleRecord:
    return SaleRecord(
        sale_key="sale:1",
        branch_id=4,
        payment_date=date(2026, 9, 10),
        phone="6861234567",
        member_id="123",
        revenue=Decimal("899"),
    )


def _row(
    *,
    event_key: str,
    origin: str | None,
    bought: bool,
) -> VisitConversionRow:
    return VisitConversionRow(
        event_key=event_key,
        branch_id=4,
        visit_date=date(2026, 9, 5),
        phone="6861234567",
        origin=origin,
        sale=_sale() if bought else None,
    )


def test_serialize_metrics_splits_iventas_and_untraced_conversion():
    rows = [
        _row(
            event_key="iv-bought",
            origin=ORIGIN_IVENTAS_META,
            bought=True,
        ),
        _row(
            event_key="iv-not-bought",
            origin=ORIGIN_IVENTAS_META,
            bought=False,
        ),
        _row(
            event_key="untraced-bought",
            origin=None,
            bought=True,
        ),
        _row(
            event_key="untraced-not-bought-1",
            origin=None,
            bought=False,
        ),
        _row(
            event_key="untraced-not-bought-2",
            origin=None,
            bought=False,
        ),
    ]

    metrics = _serialize_metrics(rows)

    assert metrics["visits_iventas_bought"] == 1
    assert metrics["visits_iventas_not_bought"] == 1
    assert metrics["visits_not_iventas_bought"] == 1
    assert metrics["visits_not_iventas_not_bought"] == 2
    assert metrics["iventas_visit_conversion_rate"] == 0.5
    assert metrics["not_iventas_visit_conversion_rate"] == 1 / 3


def test_metric_filters_match_each_visit_conversion_bucket():
    iventas_bought = _row(
        event_key="iv-bought",
        origin=ORIGIN_IVENTAS_META,
        bought=True,
    )
    untraced_not_bought = _row(
        event_key="untraced-not-bought",
        origin=None,
        bought=False,
    )

    assert _metric_matches(
        iventas_bought,
        "visits_iventas_bought",
    )
    assert not _metric_matches(
        iventas_bought,
        "visits_iventas_not_bought",
    )
    assert _metric_matches(
        untraced_not_bought,
        "visits_not_iventas_not_bought",
    )
    assert not _metric_matches(
        untraced_not_bought,
        "visits_not_iventas_bought",
    )
