from __future__ import annotations

from datetime import date
from typing import Any

from app.control_center.access import ControlScope
from app.track_alerts.services.track_regional_operational_service import (
    get_regional_operational_detail,
)
from app.warehouse.services.track_operational_forecast_service import (
    build_operational_forecast_scope_summary,
)


class ControlOperationalForecastDataError(RuntimeError):
    pass


def _normalize_branch_id(value: Any) -> int | None:
    try:
        branch_id = int(value)
    except (TypeError, ValueError):
        return None

    return branch_id if branch_id > 0 else None


def build_control_operational_forecast(
    *,
    user: Any,
    cutoff_date: date,
    effective_scope: ControlScope,
    generation_mode: str = "manual_preview",
) -> dict[str, Any]:
    regional = get_regional_operational_detail(
        user=user,
        track_date=cutoff_date,
        generation_mode=generation_mode,
    )

    allowed_branch_ids = (
        None
        if effective_scope.type == "GLOBAL"
        else set(effective_scope.branch_ids)
    )

    branch_forecasts: list[dict[str, Any]] = []
    branches: list[dict[str, Any]] = []
    seen_branch_ids: set[int] = set()

    for region in regional.get("regions") or []:
        for branch in region.get("branches") or []:
            branch_id = _normalize_branch_id(branch.get("sucursal_id"))
            if branch_id is None:
                raise ControlOperationalForecastDataError(
                    "Seguimiento Regional devolvió una sucursal sin id válido."
                )

            if (
                allowed_branch_ids is not None
                and branch_id not in allowed_branch_ids
            ):
                continue

            if branch_id in seen_branch_ids:
                raise ControlOperationalForecastDataError(
                    "Seguimiento Regional devolvió una sucursal duplicada "
                    f"para Control: {branch_id}."
                )
            seen_branch_ids.add(branch_id)

            forecast = branch.get("operational_forecast")
            if not isinstance(forecast, dict):
                raise ControlOperationalForecastDataError(
                    "La sucursal no contiene el contrato de Forecast "
                    f"Operativo: {branch_id}."
                )

            branch_forecasts.append(forecast)
            branches.append(
                {
                    "sucursal_id": branch_id,
                    "sucursal_canon": branch.get("sucursal_canon"),
                    "sucursal": branch.get("sucursal_name"),
                    "region_key": region.get("region_key"),
                    "region_label": region.get("region_label"),
                }
            )

    summary = build_operational_forecast_scope_summary(branch_forecasts)

    return {
        "status": "ok",
        "cutoff_date": cutoff_date.isoformat(),
        "generation_mode": generation_mode,
        "resolved_version": regional.get("resolved_version"),
        "summary": summary,
        "branches": branches,
    }
