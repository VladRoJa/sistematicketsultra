from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Iterable

from app.models.suite_governance import SuiteRegionORM
from app.models.warehouse import TrackBranchCatalogORM, TrackDailyMartORM
from app.track_alerts.services.track_alert_region_rules_service import (
    _get_branch_display_name,
    _load_track_rows_with_region,
)
from app.track_alerts.services.track_regional_pacing_service import (
    build_bajas_metric,
    build_clientes_nuevos_metric,
    build_linear_pace_metric,
    build_reactivaciones_metric,
    build_target_progress_metric,
    build_users_gap_metric,
)
from app.warehouse.services.track_daily_query_version_service import (
    resolve_effective_track_daily_version,
)
from app.warehouse.services.track_forecast_service import (
    build_branch_income_projection_summary,
)


class TrackRegionalOperationalDataError(RuntimeError):
    pass


@dataclass(frozen=True)
class _RegionalJoinedRow:
    mart: TrackDailyMartORM
    branch: TrackBranchCatalogORM
    region: SuiteRegionORM


def _to_optional_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _income_value(row: TrackDailyMartORM) -> Decimal | None:
    value = row.ingreso_real_total_mtd

    if value is None:
        value = row.ingreso_real_mtd

    return _to_optional_decimal(value)


def _complete_sum(values: Iterable[Any]) -> Decimal | None:
    normalized_values = [_to_optional_decimal(value) for value in values]

    if any(value is None for value in normalized_values):
        return None

    return sum(
        (value for value in normalized_values if value is not None),
        Decimal("0"),
    )


def _complete_positive_target_sum(values: Iterable[Any]) -> Decimal | None:
    normalized_values = [_to_optional_decimal(value) for value in values]

    if any(
        value is None or value <= 0
        for value in normalized_values
    ):
        return None

    return sum(
        (value for value in normalized_values if value is not None),
        Decimal("0"),
    )


def _build_metric_bundle(
    *,
    track_date: date,
    clientes_actual: Any,
    clientes_target: Any,
    reactivaciones_actual: Any,
    reactivaciones_target: Any,
    bajas_actual: Any,
    bajas_limit: Any,
    domiciliados_actual: Any,
    domiciliados_target: Any,
    ingreso_actual: Any,
    ingreso_target: Any,
    tienda_actual: Any,
    tienda_target: Any,
    usuarios_actual: Any,
    usuarios_proyeccion: Any,
) -> dict[str, Any]:
    return {
        "clientes_nuevos": build_clientes_nuevos_metric(
            actual_mtd=clientes_actual,
            monthly_target=clientes_target,
            cutoff_date=track_date,
        ).to_dict(),
        "reactivaciones": build_reactivaciones_metric(
            actual_mtd=reactivaciones_actual,
            monthly_target=reactivaciones_target,
            cutoff_date=track_date,
        ).to_dict(),
        "bajas": build_bajas_metric(
            actual_mtd=bajas_actual,
            monthly_limit=bajas_limit,
        ).to_dict(),
        "domiciliados": build_target_progress_metric(
            metric_key="domiciliados",
            actual_mtd=domiciliados_actual,
            monthly_target=domiciliados_target,
        ).to_dict(),
        "ingreso": build_target_progress_metric(
            metric_key="ingreso",
            actual_mtd=ingreso_actual,
            monthly_target=ingreso_target,
        ).to_dict(),
        "tienda": build_target_progress_metric(
            metric_key="tienda",
            actual_mtd=tienda_actual,
            monthly_target=tienda_target,
        ).to_dict(),
        "usuarios": build_users_gap_metric(
            current_users=usuarios_actual,
            projected_close_users=usuarios_proyeccion,
        ).to_dict(),
    }


def _build_branch_item(
    *,
    track_date: date,
    joined_row: _RegionalJoinedRow,
) -> dict[str, Any]:
    mart_row = joined_row.mart
    branch_row = joined_row.branch
    income_value = _income_value(mart_row)
    metrics = _build_metric_bundle(
        track_date=track_date,
        clientes_actual=mart_row.clientes_nuevos_real_mtd,
        clientes_target=mart_row.meta_clientes_nuevos_mes,
        reactivaciones_actual=mart_row.reactivaciones_real_mtd,
        reactivaciones_target=mart_row.meta_reactivaciones_mes,
        bajas_actual=mart_row.bajas_reales_mtd,
        bajas_limit=mart_row.meta_bajas_mes,
        domiciliados_actual=mart_row.nuevos_domiciliados_real_mtd,
        domiciliados_target=mart_row.meta_nuevos_domiciliados_mes,
        ingreso_actual=income_value,
        ingreso_target=mart_row.meta_faycgo_mes,
        tienda_actual=mart_row.venta_tienda_real_mtd,
        tienda_target=mart_row.meta_venta_tienda_mes,
        usuarios_actual=mart_row.usuarios_activos_actual,
        usuarios_proyeccion=mart_row.proyeccion_usuarios_cierre_mes,
    )
    metrics["ingreso"]["projection"] = (
        build_branch_income_projection_summary(
            sucursal_canon=branch_row.sucursal_canon,
            target_month=track_date.replace(day=1),
            cutoff_day=track_date.day,
            current_income_mtd=income_value,
        )
    )

    sucursal = getattr(branch_row, "sucursal", None)

    return {
        "sucursal_id": branch_row.sucursal_id,
        "sucursal_canon": branch_row.sucursal_canon,
        "sucursal_name": _get_branch_display_name(branch_row),
        "orden_apertura": (
            getattr(sucursal, "orden_apertura", None)
            if sucursal is not None
            else None
        ),
        "metrics": metrics,
    }


def _build_region_summary(
    *,
    track_date: date,
    rows: list[_RegionalJoinedRow],
) -> dict[str, Any]:
    marts = [row.mart for row in rows]
    metrics = _build_metric_bundle(
        track_date=track_date,
        clientes_actual=_complete_sum(
            row.clientes_nuevos_real_mtd for row in marts
        ),
        clientes_target=_complete_positive_target_sum(
            row.meta_clientes_nuevos_mes for row in marts
        ),
        reactivaciones_actual=_complete_sum(
            row.reactivaciones_real_mtd for row in marts
        ),
        reactivaciones_target=_complete_positive_target_sum(
            row.meta_reactivaciones_mes for row in marts
        ),
        bajas_actual=_complete_sum(row.bajas_reales_mtd for row in marts),
        bajas_limit=_complete_positive_target_sum(
            row.meta_bajas_mes for row in marts
        ),
        domiciliados_actual=_complete_sum(
            row.nuevos_domiciliados_real_mtd for row in marts
        ),
        domiciliados_target=_complete_positive_target_sum(
            row.meta_nuevos_domiciliados_mes for row in marts
        ),
        ingreso_actual=_complete_sum(_income_value(row) for row in marts),
        ingreso_target=_complete_positive_target_sum(
            row.meta_faycgo_mes for row in marts
        ),
        tienda_actual=_complete_sum(
            row.venta_tienda_real_mtd for row in marts
        ),
        tienda_target=_complete_positive_target_sum(
            row.meta_venta_tienda_mes for row in marts
        ),
        usuarios_actual=_complete_sum(
            row.usuarios_activos_actual for row in marts
        ),
        usuarios_proyeccion=_complete_sum(
            row.proyeccion_usuarios_cierre_mes for row in marts
        ),
    )

    return {
        "total_branches": len(rows),
        "metrics": metrics,
    }


def _pace_priority_item(
    *,
    region_key: str,
    region_label: str,
    branch: dict[str, Any],
    metric_key: str,
) -> dict[str, Any] | None:
    metric = branch["metrics"][metric_key]
    gap_pct_points = _to_optional_decimal(metric.get("gap_pct_points"))

    return {
        "region_key": region_key,
        "region_label": region_label,
        "sucursal_canon": branch["sucursal_canon"],
        "sucursal_name": branch["sucursal_name"],
        "metric_key": metric_key,
        "actual_mtd": metric["actual_mtd"],
        "monthly_target": metric["monthly_target"],
        "actual_progress_pct": metric["actual_progress_pct"],
        "expected_progress_pct": metric["expected_progress_pct"],
        "expected_mtd": metric["expected_mtd"],
        "gap_units": metric["gap_units"],
        "gap_pct_points": metric["gap_pct_points"],
        "status": metric["status"],
    }


def _domiciliados_priority_item(
    *,
    region_key: str,
    region_label: str,
    branch: dict[str, Any],
    track_date: date,
) -> dict[str, Any]:
    metric = branch["metrics"]["domiciliados"]

    pace_metric = build_linear_pace_metric(
        metric_key="domiciliados",
        actual_mtd=metric.get("actual_mtd"),
        monthly_target=metric.get("monthly_target"),
        cutoff_date=track_date,
    ).to_dict()

    return {
        "region_key": region_key,
        "region_label": region_label,
        "sucursal_canon": branch["sucursal_canon"],
        "sucursal_name": branch["sucursal_name"],
        "metric_key": "domiciliados",
        "actual_mtd": pace_metric["actual_mtd"],
        "monthly_target": pace_metric["monthly_target"],
        "actual_progress_pct": pace_metric["actual_progress_pct"],
        "expected_progress_pct": pace_metric["expected_progress_pct"],
        "expected_mtd": pace_metric["expected_mtd"],
        "gap_units": pace_metric["gap_units"],
        "gap_pct_points": pace_metric["gap_pct_points"],
        "status": pace_metric["status"],
    }


def _bajas_priority_item(
    *,
    region_key: str,
    region_label: str,
    branch: dict[str, Any],
) -> dict[str, Any] | None:
    metric = branch["metrics"]["bajas"]

    actual = _to_optional_decimal(metric["actual_mtd"])
    limit = _to_optional_decimal(metric["monthly_limit"])
    limit_usage_pct = _to_optional_decimal(metric["limit_usage_pct"])

    return {
        "region_key": region_key,
        "region_label": region_label,
        "sucursal_canon": branch["sucursal_canon"],
        "sucursal_name": branch["sucursal_name"],
        "metric_key": "bajas",
        "actual_mtd": metric["actual_mtd"],
        "monthly_limit": metric["monthly_limit"],
        "limit_usage_pct": metric["limit_usage_pct"],
        "excess_units": (
            str(actual - limit)
            if (
                actual is not None
                and limit is not None
                and actual > limit
            )
            else None
        ),
        "status": (
            (
                "LIMITE_EXCEDIDO"
                if actual > limit
                else "DENTRO_LIMITE"
            )
            if (
                actual is not None
                and limit is not None
                and limit > 0
            )
            else metric["status"]
        ),
    }


def _build_priorities(
    regions: list[dict[str, Any]],
    *,
    track_date: date | None = None,
) -> list[dict[str, Any]]:
    pace_items: dict[str, list[dict[str, Any]]] = {
        "clientes_nuevos": [],
        "reactivaciones": [],
    }
    bajas_items: list[dict[str, Any]] = []
    domiciliados_items: list[dict[str, Any]] = []

    for region in regions:
        for branch in region["branches"]:
            for metric_key in pace_items:
                priority = _pace_priority_item(
                    region_key=region["region_key"],
                    region_label=region["region_label"],
                    branch=branch,
                    metric_key=metric_key,
                )
                if priority is not None:
                    pace_items[metric_key].append(priority)

            if track_date is not None:
                domiciliados_items.append(
                    _domiciliados_priority_item(
                        region_key=region["region_key"],
                        region_label=region["region_label"],
                        branch=branch,
                        track_date=track_date,
                    )
                )

            bajas_priority = _bajas_priority_item(
                region_key=region["region_key"],
                region_label=region["region_label"],
                branch=branch,
            )
            if bajas_priority is not None:
                bajas_items.append(bajas_priority)

    for items in [*pace_items.values(), domiciliados_items]:
        items.sort(
            key=lambda item: (
                _to_optional_decimal(
                    item.get("gap_pct_points")
                ) is None,
                (
                    _to_optional_decimal(
                        item.get("gap_pct_points")
                    )
                    if _to_optional_decimal(
                        item.get("gap_pct_points")
                    ) is not None
                    else Decimal("0")
                ),
            ),
        )

    bajas_items.sort(
        key=lambda item: (
            _to_optional_decimal(
                item.get("limit_usage_pct")
            ) is None,
            (
                -_to_optional_decimal(
                    item.get("limit_usage_pct")
                )
                if _to_optional_decimal(
                    item.get("limit_usage_pct")
                ) is not None
                else Decimal("0")
            ),
        ),
    )

    return [
        {
            "metric_key": "clientes_nuevos",
            "metric_label": "Clientes nuevos",
            "items": pace_items["clientes_nuevos"],
        },
        {
            "metric_key": "reactivaciones",
            "metric_label": "Reactivaciones",
            "items": pace_items["reactivaciones"],
        },
        {
            "metric_key": "bajas",
            "metric_label": "Bajas",
            "items": bajas_items,
        },
        {
            "metric_key": "domiciliados",
            "metric_label": "Domiciliados",
            "items": domiciliados_items,
        },
    ]


def _business_rules() -> list[dict[str, str]]:
    return [
        {
            "key": "version_resolution",
            "label": "Versión efectiva del Track",
            "description": (
                "La consulta usa una sola TrackDailyVersion: preview operativo "
                "para el día actual y cierre canónico, con fallback a base "
                "nocturna canónica, para históricos."
            ),
        },
        {
            "key": "clientes_nuevos_weekday",
            "label": "Ritmo de Clientes nuevos",
            "description": (
                "Usa su curva histórica weekday aprobada, normalizada sobre "
                "todos los días naturales del mes."
            ),
        },
        {
            "key": "reactivaciones_weekday",
            "label": "Ritmo de Reactivaciones",
            "description": (
                "Usa una curva weekday propia, normalizada sobre todos los "
                "días naturales del mes."
            ),
        },
        {
            "key": "bajas_limit",
            "label": "Límite de Bajas",
            "description": (
                "Bajas muestra todas las sucursales ordenadas por consumo "
                "del límite mensual: primero las excedidas y después las "
                "más cercanas al límite, sin umbrales artificiales."
            ),
        },
        {
            "key": "domiciliados_linear_pace",
            "label": "Ritmo de Domiciliados",
            "description": (
                "Usa pacing lineal por día calendario: el avance esperado "
                "es día del mes dividido entre días naturales del mes."
            ),
        },
        {
            "key": "income_source",
            "label": "Ingreso oficial",
            "description": (
                "Usa ingreso_real_total_mtd y solo aplica el fallback "
                "transitorio a ingreso_real_mtd cuando el total es nulo."
            ),
        },
        {
            "key": "income_projection",
            "label": "Proyección de Ingreso",
            "description": (
                "Reutiliza el ritmo histórico estable de Forecast y no "
                "proyecta cuando la historia comparable es insuficiente."
            ),
        },
        {
            "key": "tienda_no_curve",
            "label": "Tienda",
            "description": "Tienda muestra avance contra meta sin curva weekday ni forecast.",
        },
        {
            "key": "users_gap",
            "label": "Brecha de usuarios",
            "description": (
                "Muestra usuarios activos menos proyección de cierre; no "
                "genera alerta de ocupación ni utiliza m²."
            ),
        },
    ]


def get_regional_operational_detail(
    *,
    track_date: date,
    generation_mode: str = "manual_preview",
) -> dict[str, Any]:
    resolved_version = resolve_effective_track_daily_version(
        track_date=track_date,
        generation_mode=generation_mode,
    )

    if resolved_version is None:
        return {
            "track_date": track_date.isoformat(),
            "generation_mode": generation_mode,
            "resolved_version": None,
            "regions": [],
            "priorities": _build_priorities(
                [],
                track_date=track_date,
            ),
            "business_rules": _business_rules(),
        }

    raw_joined_rows = _load_track_rows_with_region(
        track_daily_version_id=resolved_version.id,
    )
    joined_rows = [
        _RegionalJoinedRow(mart=mart, branch=branch, region=region)
        for mart, branch, region in raw_joined_rows
    ]
    target_month = track_date.replace(day=1)
    seen_branches: set[str] = set()
    rows_by_region: dict[str, list[_RegionalJoinedRow]] = {}

    for joined_row in joined_rows:
        mart_target_month = getattr(joined_row.mart, "target_month", None)
        if mart_target_month is not None and mart_target_month != target_month:
            raise TrackRegionalOperationalDataError(
                "La versión resuelta contiene una fila con target_month "
                "distinto al mes consultado."
            )

        branch_key = joined_row.branch.sucursal_canon
        if branch_key in seen_branches:
            raise TrackRegionalOperationalDataError(
                f"La sucursal {branch_key!r} tiene más de una región current."
            )
        seen_branches.add(branch_key)
        rows_by_region.setdefault(joined_row.region.region_key, []).append(
            joined_row
        )

    regions: list[dict[str, Any]] = []

    for region_rows in rows_by_region.values():
        region_row = region_rows[0].region
        branches = [
            _build_branch_item(track_date=track_date, joined_row=row)
            for row in region_rows
        ]
        branches.sort(
            key=lambda branch: (
                branch["orden_apertura"] or 9999,
                branch["sucursal_name"],
            )
        )
        regions.append(
            {
                "region_key": region_row.region_key,
                "region_label": region_row.region_label,
                "summary": _build_region_summary(
                    track_date=track_date,
                    rows=region_rows,
                ),
                "branches": branches,
            }
        )

    regions.sort(key=lambda region: region["region_label"])

    return {
        "track_date": track_date.isoformat(),
        "generation_mode": generation_mode,
        "resolved_version": {
            "id": resolved_version.id,
            "version_type": resolved_version.version_type,
            "status": resolved_version.status,
        },
        "regions": regions,
        "priorities": _build_priorities(
            regions,
            track_date=track_date,
        ),
        "business_rules": _business_rules(),
    }
