from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable

from app.warehouse.services.socios_activos_sync_service import (
    sync_socios_activos_daily,
)
from app.warehouse.services.socios_vencidos_cartera_sync_service import (
    sync_socios_vencidos_daily,
)


def run_job(
    *,
    business_date: date,
    requested_by: str | None = None,
    activos_sync: Callable[..., dict[str, Any]] = sync_socios_activos_daily,
    vencidos_sync: Callable[..., dict[str, Any]] = sync_socios_vencidos_daily,
) -> dict[str, Any]:
    if not isinstance(business_date, date):
        raise ValueError("business_date debe ser date.")

    socios_activos_date = business_date
    socios_vencidos_date = business_date - timedelta(days=1)

    activos_result = activos_sync(
        business_date=socios_activos_date,
        requested_by=requested_by,
    )

    vencidos_result = vencidos_sync(
        business_date=socios_vencidos_date,
        requested_by=requested_by,
    )

    return {
        "status": "completed",
        "business_date": business_date.isoformat(),
        "socios_activos_business_date": socios_activos_date.isoformat(),
        "socios_vencidos_business_date": socios_vencidos_date.isoformat(),
        "socios_activos": activos_result,
        "socios_vencidos": vencidos_result,
    }
