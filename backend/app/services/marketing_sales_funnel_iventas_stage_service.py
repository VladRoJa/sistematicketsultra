from __future__ import annotations

from datetime import date

from app.extensions import db
from app.models import MarketingIventasContactORM
from app.services.marketing_sales_funnel_service import (
    _canonical_runs_for_window,
    _month_end,
)


def count_monthly_iventas_leads(
    *,
    month_start: date,
    branch_ids: tuple[int, ...],
) -> int:
    """Count unique iVentas leads whose first message happened in the month.

    A lead is unique by KPI branch + normalized 10-digit phone. The source is the
    canonical iVentas run for the requested month; historical contacts carried by
    the run are excluded with first_message_date_local at query time.
    """
    if not branch_ids:
        return 0

    month_end = _month_end(month_start)
    period_key = f"IVENTAS-{month_start.strftime('%Y-%m')}"
    runs = _canonical_runs_for_window(month_start, month_end)
    run_ids = tuple(
        int(run.id)
        for run in runs
        if str(run.period_key) == period_key
    )
    if not run_ids:
        return 0

    return int(
        db.session.query(
            MarketingIventasContactORM.sucursal_id,
            MarketingIventasContactORM.phone_mx10,
        )
        .filter(
            MarketingIventasContactORM.sync_run_id.in_(run_ids),
            MarketingIventasContactORM.sucursal_id.in_(branch_ids),
            MarketingIventasContactORM.first_message_at_utc.isnot(None),
            MarketingIventasContactORM.first_message_date_local.isnot(None),
            MarketingIventasContactORM.first_message_date_local >= month_start,
            MarketingIventasContactORM.first_message_date_local <= month_end,
            MarketingIventasContactORM.phone_mx10.isnot(None),
            MarketingIventasContactORM.phone_mx10 != "",
        )
        .distinct()
        .count()
    )
