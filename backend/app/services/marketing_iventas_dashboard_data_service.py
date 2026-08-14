"""Adaptador de datos iVentas para el dashboard de Marketing."""

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.extensions import db
from app.models import MarketingIventasSyncRunORM
from app.services.marketing_iventas_leads_service import (
    MarketingIventasCanonicalRunRequiredError,
    MarketingIventasLeadMetrics,
    MarketingIventasLeadMetricsByBranchMonth,
    list_iventas_lead_metrics_by_branch_month_for_run,
    read_canonical_iventas_lead_metrics,
)
from app.services.marketing_iventas_period_service import (
    resolve_iventas_month_period,
)


@dataclass(frozen=True)
class MarketingIventasDashboardMonthData:
    available: bool
    period_key: str
    date_from: date
    date_to: date
    sync_run_id: int | None
    metrics: MarketingIventasLeadMetrics | None
    branch_metrics: tuple[
        MarketingIventasLeadMetricsByBranchMonth,
        ...,
    ] | None


def read_iventas_dashboard_month_data(
    *,
    month_date: date,
    today: date,
    session: Any | None = None,
) -> MarketingIventasDashboardMonthData:
    """Lee el snapshot mensual iVentas disponible para dashboard.

    La ausencia de canónico se representa como available=False.
    Nunca se transforma en métricas cero.
    """

    period = resolve_iventas_month_period(
        month_date=month_date,
        today=today,
    )

    try:
        metrics = read_canonical_iventas_lead_metrics(
            period_key=period.period_key,
            session=session,
        )
    except MarketingIventasCanonicalRunRequiredError:
        return MarketingIventasDashboardMonthData(
            available=False,
            period_key=period.period_key,
            date_from=period.date_from,
            date_to=period.date_to,
            sync_run_id=None,
            metrics=None,
            branch_metrics=None,
        )

    session_value = (
        session
        if session is not None
        else db.session
    )

    snapshot_run = session_value.get(
        MarketingIventasSyncRunORM,
        metrics.sync_run_id,
    )

    if snapshot_run is None:
        raise RuntimeError(
            "El snapshot iVentas canónico leído "
            "ya no existe."
        )

    branch_metrics = (
        list_iventas_lead_metrics_by_branch_month_for_run(
            sync_run_id=metrics.sync_run_id,
            period_key=period.period_key,
            session=session_value,
        )
    )

    return MarketingIventasDashboardMonthData(
        available=True,
        period_key=period.period_key,
        date_from=snapshot_run.date_from,
        date_to=snapshot_run.date_to,
        sync_run_id=metrics.sync_run_id,
        metrics=metrics,
        branch_metrics=branch_metrics,
    )
