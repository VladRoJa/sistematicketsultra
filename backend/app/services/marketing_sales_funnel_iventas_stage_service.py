from __future__ import annotations

from datetime import date

from app.models import MarketingIventasContactORM
from app.services.marketing_sales_funnel_service import (
    _canonical_runs_for_window,
    _month_end,
)


def _is_monthly_iventas_lead(
    contact: MarketingIventasContactORM,
    month_start: date,
) -> bool:
    interaction_date = contact.first_message_date_local
    phone = str(contact.phone_mx10 or "").strip()
    if interaction_date is None or not phone:
        return False
    return month_start <= interaction_date <= _month_end(month_start)


def count_monthly_iventas_leads(
    *,
    month_start: date,
    branch_ids: tuple[int, ...],
) -> int:
    """Count unique iVentas leads whose first message happened in the month.

    A lead is unique by KPI branch + normalized 10-digit phone. The source is the
    canonical iVentas run for the requested month; older contacts carried by the
    run are excluded by first_message_date_local.
    """
    if not branch_ids:
        return 0

    period_key = f"IVENTAS-{month_start.strftime('%Y-%m')}"
    runs = _canonical_runs_for_window(month_start, _month_end(month_start))
    run_ids = tuple(
        int(run.id)
        for run in runs
        if str(run.period_key) == period_key
    )
    if not run_ids:
        return 0

    contacts = (
        MarketingIventasContactORM.query.filter(
            MarketingIventasContactORM.sync_run_id.in_(run_ids),
            MarketingIventasContactORM.sucursal_id.in_(branch_ids),
            MarketingIventasContactORM.first_message_at_utc.isnot(None),
            MarketingIventasContactORM.phone_mx10.isnot(None),
        )
        .all()
    )

    lead_keys: set[tuple[int, str]] = set()
    for contact in contacts:
        if not _is_monthly_iventas_lead(contact, month_start):
            continue
        lead_keys.add(
            (
                int(contact.sucursal_id),
                str(contact.phone_mx10).strip(),
            )
        )

    return len(lead_keys)
