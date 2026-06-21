#backend\app\warehouse\services\kpi_desempeno_query_service.py


from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.models.warehouse import (
    KpiDesempenoSnapshotORM,
    KpiDesempenoSnapshotRowORM,
    TrackBranchCatalogORM,
    TrackDailyMartORM,
)
from app.warehouse.services.track_branch_alias_resolver_service import (
    resolve_track_branch_alias,
)


KPI_DESEMPENO_REPORT_TYPE_KEY = "kpi_desempeno"
KPI_DESEMPENO_SNAPSHOT_KIND = "daily"
KPI_DESEMPENO_ALIAS_SOURCE_FAMILY = "gasca_family"

OUT_OF_SCOPE_RAW_BRANCHES = {
    "BECA",
}


class KpiDesempenoQueryServiceError(RuntimeError):
    """Error base para consultas BI de KPI Desempeño."""


def _ensure_target_month(value: Any) -> tuple[int, int, str]:
    raw_value = str(value or "").strip()

    if not raw_value:
        raise KpiDesempenoQueryServiceError("target_month es obligatorio.")

    parts = raw_value.split("-")

    if len(parts) != 2:
        raise KpiDesempenoQueryServiceError(
            "target_month debe venir en formato YYYY-MM."
        )

    try:
        year = int(parts[0])
        month = int(parts[1])
    except Exception as exc:
        raise KpiDesempenoQueryServiceError(
            f"target_month inválido: {raw_value!r}."
        ) from exc

    if month < 1 or month > 12:
        raise KpiDesempenoQueryServiceError(
            f"Mes inválido en target_month: {raw_value!r}."
        )

    normalized_target_month = f"{year:04d}-{month:02d}"

    return year, month, normalized_target_month


def _month_bounds(*, year: int, month: int) -> tuple[date, date]:
    start_date = date(year, month, 1)

    if month == 12:
        next_month_start = date(year + 1, 1, 1)
    else:
        next_month_start = date(year, month + 1, 1)

    return start_date, next_month_start


def _normalize_raw_branch_name(value: Any) -> str:
    return str(value or "").strip()


def _is_out_of_scope_raw_branch(raw_branch_name: str) -> bool:
    normalized = raw_branch_name.strip().upper()
    return normalized in OUT_OF_SCOPE_RAW_BRANCHES


def _resolve_last_canonical_snapshot_for_month(
    *,
    year: int,
    month: int,
) -> KpiDesempenoSnapshotORM | None:
    start_date, next_month_start = _month_bounds(year=year, month=month)

    return (
        KpiDesempenoSnapshotORM.query.filter(
            KpiDesempenoSnapshotORM.report_type_key == KPI_DESEMPENO_REPORT_TYPE_KEY,
            KpiDesempenoSnapshotORM.snapshot_kind == KPI_DESEMPENO_SNAPSHOT_KIND,
            KpiDesempenoSnapshotORM.is_canonical.is_(True),
            KpiDesempenoSnapshotORM.business_date >= start_date,
            KpiDesempenoSnapshotORM.business_date < next_month_start,
        )
        .order_by(
            KpiDesempenoSnapshotORM.business_date.desc(),
            KpiDesempenoSnapshotORM.id.desc(),
        )
        .first()
    )


def _fetch_snapshot_rows(
    *,
    snapshot_id: int,
) -> list[KpiDesempenoSnapshotRowORM]:
    return (
        KpiDesempenoSnapshotRowORM.query.filter_by(snapshot_id=snapshot_id)
        .order_by(KpiDesempenoSnapshotRowORM.row_index.asc())
        .all()
    )


def _fetch_branch_catalog_by_canon(
    *,
    sucursales_canon: set[str],
) -> dict[str, TrackBranchCatalogORM]:
    if not sucursales_canon:
        return {}

    branches = (
        TrackBranchCatalogORM.query.filter(
            TrackBranchCatalogORM.sucursal_canon.in_(sorted(sucursales_canon))
        )
        .all()
    )

    return {branch.sucursal_canon: branch for branch in branches}



def _fetch_branch_capacity_targets_by_canon(
    *,
    sucursales_canon: set[str],
    target_month: Any,
) -> dict[str, dict[str, Any]]:
    if not sucursales_canon:
        return {}

    target_year, target_month_number, _ = _ensure_target_month(target_month)
    normalized_target_month, _ = _month_bounds(
        year=target_year,
        month=target_month_number,
    )

    capacity_by_canon: dict[str, dict[str, Any]] = {}

    for sucursal_canon in sorted(sucursales_canon):
        mart_row = (
            TrackDailyMartORM.query.filter(
                TrackDailyMartORM.sucursal_canon == sucursal_canon,
                TrackDailyMartORM.target_month <= normalized_target_month,
                TrackDailyMartORM.m2_sin_circulaciones.isnot(None),
            )
            .order_by(
                TrackDailyMartORM.track_date.desc(),
                TrackDailyMartORM.id.desc(),
            )
            .first()
        )

        if mart_row is None or mart_row.m2_sin_circulaciones is None:
            continue

        m2_value = float(mart_row.m2_sin_circulaciones)

        capacity_by_canon[sucursal_canon] = {
            "m2_sin_circulaciones": m2_value,
            "target_1_5": round(m2_value * 1.5),
            "target_2_0": round(m2_value * 2.0),
            "source": {
                "track_daily_mart_id": mart_row.id,
                "track_date": mart_row.track_date.isoformat(),
                "target_month": mart_row.target_month.isoformat(),
            },
        }

    return capacity_by_canon

def _resolve_rows_branch_canon(
    *,
    rows: list[KpiDesempenoSnapshotRowORM],
) -> tuple[dict[int, str | None], list[dict[str, Any]]]:
    canon_by_row_id: dict[int, str | None] = {}
    warnings: list[dict[str, Any]] = []

    for row in rows:
        raw_branch_name = _normalize_raw_branch_name(row.sucursal)

        if _is_out_of_scope_raw_branch(raw_branch_name):
            canon_by_row_id[row.id] = None
            continue

        sucursal_canon = resolve_track_branch_alias(
            source_family=KPI_DESEMPENO_ALIAS_SOURCE_FAMILY,
            raw_branch_name=raw_branch_name,
        )

        canon_by_row_id[row.id] = sucursal_canon

        if sucursal_canon is None:
            warnings.append(
                {
                    "code": "missing_branch_alias",
                    "message": "No se encontró alias Track para una sucursal KPI.",
                    "sucursal_raw": raw_branch_name,
                    "source_family": KPI_DESEMPENO_ALIAS_SOURCE_FAMILY,
                }
            )

    return canon_by_row_id, warnings


def _build_branch_payload(
    *,
    row: KpiDesempenoSnapshotRowORM,
    sucursal_canon: str | None,
    branch_catalog_by_canon: dict[str, TrackBranchCatalogORM],
    capacity_by_canon: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    branch_catalog = (
        branch_catalog_by_canon.get(sucursal_canon)
        if sucursal_canon
        else None
    )

    track_label = (
        branch_catalog.track_label
        if branch_catalog is not None
        else _normalize_raw_branch_name(row.sucursal)
    )

    capacity = (
        capacity_by_canon.get(sucursal_canon)
        if capacity_by_canon is not None and sucursal_canon
        else None
    )

    return {
        "sucursal_raw": _normalize_raw_branch_name(row.sucursal),
        "sucursal_canon": sucursal_canon,
        "track_label": track_label,
        "display_order": (
            branch_catalog.display_order
            if branch_catalog is not None
            else None
        ),
        "is_track_active": (
            branch_catalog.is_track_active
            if branch_catalog is not None
            else None
        ),
        "capacity": capacity,
    }


def _build_monthly_row_payload(
    *,
    row: KpiDesempenoSnapshotRowORM,
    snapshot: KpiDesempenoSnapshotORM,
    sucursal_canon: str | None,
    branch_catalog_by_canon: dict[str, TrackBranchCatalogORM],
) -> dict[str, Any]:
    socios_inicio = int(row.socios_activos_inicio_mes or 0)
    socios_cierre = int(row.socios_activos_del_mes or 0)
    clientes_nuevos = int(row.clientes_nuevo_real or 0)
    reactivaciones = int(row.reactivaciones or 0)
    bajas = int(row.bajas or 0)

    crecimiento_real = socios_cierre - socios_inicio
    movimiento_reportado = clientes_nuevos + reactivaciones - bajas
    ajuste_no_explicado = crecimiento_real - movimiento_reportado

    return {
        "branch": _build_branch_payload(
            row=row,
            sucursal_canon=sucursal_canon,
            branch_catalog_by_canon=branch_catalog_by_canon,
        ),
        "metrics": {
            "socios_activos_inicio_mes": socios_inicio,
            "socios_activos_cierre_mes": socios_cierre,
            "clientes_nuevos": clientes_nuevos,
            "reactivaciones": reactivaciones,
            "bajas": bajas,
            "crecimiento_real": crecimiento_real,
            "movimiento_reportado": movimiento_reportado,
            "ajuste_no_explicado": ajuste_no_explicado,
        },
        "source": {
            "snapshot_id": snapshot.id,
            "business_date": snapshot.business_date.isoformat(),
            "report_type_key": snapshot.report_type_key,
            "snapshot_kind": snapshot.snapshot_kind,
            "is_canonical": snapshot.is_canonical,
        },
    }


def _sort_monthly_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda item: (
            item["branch"]["display_order"]
            if item["branch"]["display_order"] is not None
            else 999999,
            item["branch"]["track_label"] or "",
            item["branch"]["sucursal_raw"] or "",
        ),
    )


def _build_totals(rows: list[dict[str, Any]]) -> dict[str, int]:
    metric_keys = [
        "socios_activos_inicio_mes",
        "socios_activos_cierre_mes",
        "clientes_nuevos",
        "reactivaciones",
        "bajas",
        "crecimiento_real",
        "movimiento_reportado",
        "ajuste_no_explicado",
    ]

    totals: dict[str, int] = {}

    for metric_key in metric_keys:
        totals[metric_key] = sum(
            int(row["metrics"].get(metric_key) or 0)
            for row in rows
        )

    return totals


def build_monthly_closing_section(
    *,
    target_month: Any,
) -> dict[str, Any]:
    year, month, normalized_target_month = _ensure_target_month(target_month)

    snapshot = _resolve_last_canonical_snapshot_for_month(
        year=year,
        month=month,
    )

    if snapshot is None:
        return {
            "key": "monthly_closing",
            "title": "Cierre mensual de socios",
            "chart_type": "grouped_bar",
            "status": "empty",
            "target_month": normalized_target_month,
            "rule": {
                "description": "Último snapshot canónico disponible dentro del mes.",
                "report_type_key": KPI_DESEMPENO_REPORT_TYPE_KEY,
                "snapshot_kind": KPI_DESEMPENO_SNAPSHOT_KIND,
                "canonical_only": True,
            },
            "resolved_snapshot": None,
            "warnings": [
                {
                    "code": "no_canonical_snapshot_for_month",
                    "message": "No existe snapshot canónico KPI Desempeño para el mes solicitado.",
                    "target_month": normalized_target_month,
                }
            ],
            "totals": {},
            "data": [],
        }

    raw_rows = _fetch_snapshot_rows(snapshot_id=snapshot.id)
    rows = [
        row
        for row in raw_rows
        if not _is_out_of_scope_raw_branch(_normalize_raw_branch_name(row.sucursal))
    ]

    canon_by_row_id, warnings = _resolve_rows_branch_canon(rows=rows)

    sucursales_canon = {
        sucursal_canon
        for sucursal_canon in canon_by_row_id.values()
        if sucursal_canon
    }

    branch_catalog_by_canon = _fetch_branch_catalog_by_canon(
        sucursales_canon=sucursales_canon,
    )

    data = [
        _build_monthly_row_payload(
            row=row,
            snapshot=snapshot,
            sucursal_canon=canon_by_row_id.get(row.id),
            branch_catalog_by_canon=branch_catalog_by_canon,
        )
        for row in rows
    ]

    sorted_data = _sort_monthly_rows(data)

    return {
        "key": "monthly_closing",
        "title": "Cierre mensual de socios",
        "chart_type": "grouped_bar",
        "status": "ok",
        "target_month": normalized_target_month,
        "rule": {
            "description": "Último snapshot canónico disponible dentro del mes.",
            "report_type_key": KPI_DESEMPENO_REPORT_TYPE_KEY,
            "snapshot_kind": KPI_DESEMPENO_SNAPSHOT_KIND,
            "canonical_only": True,
            "metric": "socios_activos_del_mes",
        },
        "resolved_snapshot": {
            "snapshot_id": snapshot.id,
            "business_date": snapshot.business_date.isoformat(),
            "captured_at": (
                snapshot.captured_at.isoformat()
                if snapshot.captured_at
                else None
            ),
            "row_count_valid": snapshot.row_count_valid,
            "row_count_rejected": snapshot.row_count_rejected,
        },
        "warnings": warnings,
        "totals": _build_totals(sorted_data),
        "data": sorted_data,
    }


def _month_end_date(*, year: int, month: int) -> date:
    _, next_month_start = _month_bounds(year=year, month=month)
    return next_month_start - timedelta(days=1)


def _iter_month_week_ranges(
    *,
    year: int,
    month: int,
) -> list[dict[str, Any]]:
    month_start, _ = _month_bounds(year=year, month=month)
    month_end = _month_end_date(year=year, month=month)

    ranges: list[dict[str, Any]] = []
    week_number = 1
    current_start = month_start

    while current_start <= month_end:
        current_end = min(
            current_start + timedelta(days=6),
            month_end,
        )

        ranges.append(
            {
                "period_key": f"W{week_number}",
                "label": f"Semana {week_number}",
                "date_from": current_start,
                "date_to": current_end,
            }
        )

        week_number += 1
        current_start = current_end + timedelta(days=1)

    return ranges


def _resolve_last_canonical_snapshot_for_date_range(
    *,
    start_date: date,
    end_date: date,
) -> KpiDesempenoSnapshotORM | None:
    return (
        KpiDesempenoSnapshotORM.query.filter(
            KpiDesempenoSnapshotORM.report_type_key == KPI_DESEMPENO_REPORT_TYPE_KEY,
            KpiDesempenoSnapshotORM.snapshot_kind == KPI_DESEMPENO_SNAPSHOT_KIND,
            KpiDesempenoSnapshotORM.is_canonical.is_(True),
            KpiDesempenoSnapshotORM.business_date >= start_date,
            KpiDesempenoSnapshotORM.business_date <= end_date,
        )
        .order_by(
            KpiDesempenoSnapshotORM.business_date.desc(),
            KpiDesempenoSnapshotORM.id.desc(),
        )
        .first()
    )


def _build_weekly_period_payload(
    *,
    period: dict[str, Any],
    snapshot: KpiDesempenoSnapshotORM | None,
) -> dict[str, Any]:
    return {
        "period_key": period["period_key"],
        "label": period["label"],
        "date_from": period["date_from"].isoformat(),
        "date_to": period["date_to"].isoformat(),
        "resolved_snapshot": (
            {
                "snapshot_id": snapshot.id,
                "business_date": snapshot.business_date.isoformat(),
                "captured_at": (
                    snapshot.captured_at.isoformat()
                    if snapshot.captured_at
                    else None
                ),
                "row_count_valid": snapshot.row_count_valid,
                "row_count_rejected": snapshot.row_count_rejected,
            }
            if snapshot is not None
            else None
        ),
    }


def _build_weekly_row_payload(
    *,
    row: KpiDesempenoSnapshotRowORM,
    snapshot: KpiDesempenoSnapshotORM,
    period: dict[str, Any],
    sucursal_canon: str | None,
    branch_catalog_by_canon: dict[str, TrackBranchCatalogORM],
) -> dict[str, Any]:
    socios_inicio = int(row.socios_activos_inicio_mes or 0)
    socios_cierre = int(row.socios_activos_del_mes or 0)
    clientes_nuevos = int(row.clientes_nuevo_real or 0)
    reactivaciones = int(row.reactivaciones or 0)
    bajas = int(row.bajas or 0)

    crecimiento_real = socios_cierre - socios_inicio
    movimiento_reportado = clientes_nuevos + reactivaciones - bajas
    ajuste_no_explicado = crecimiento_real - movimiento_reportado

    return {
        "period": {
            "period_key": period["period_key"],
            "label": period["label"],
            "date_from": period["date_from"].isoformat(),
            "date_to": period["date_to"].isoformat(),
        },
        "branch": _build_branch_payload(
            row=row,
            sucursal_canon=sucursal_canon,
            branch_catalog_by_canon=branch_catalog_by_canon,
        ),
        "metrics": {
            "socios_activos_inicio_mes": socios_inicio,
            "socios_activos_cierre_semana": socios_cierre,
            "clientes_nuevos_mtd": clientes_nuevos,
            "reactivaciones_mtd": reactivaciones,
            "bajas_mtd": bajas,
            "crecimiento_real_mtd": crecimiento_real,
            "movimiento_reportado_mtd": movimiento_reportado,
            "ajuste_no_explicado_mtd": ajuste_no_explicado,
        },
        "source": {
            "snapshot_id": snapshot.id,
            "business_date": snapshot.business_date.isoformat(),
            "report_type_key": snapshot.report_type_key,
            "snapshot_kind": snapshot.snapshot_kind,
            "is_canonical": snapshot.is_canonical,
        },
    }


def _sort_weekly_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda item: (
            item["period"]["period_key"],
            item["branch"]["display_order"]
            if item["branch"]["display_order"] is not None
            else 999999,
            item["branch"]["track_label"] or "",
            item["branch"]["sucursal_raw"] or "",
        ),
    )


def _build_weekly_totals(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    totals_by_period: dict[str, dict[str, int]] = {}

    metric_keys = [
        "socios_activos_inicio_mes",
        "socios_activos_cierre_semana",
        "clientes_nuevos_mtd",
        "reactivaciones_mtd",
        "bajas_mtd",
        "crecimiento_real_mtd",
        "movimiento_reportado_mtd",
        "ajuste_no_explicado_mtd",
    ]

    for row in rows:
        period_key = str(row["period"]["period_key"])

        if period_key not in totals_by_period:
            totals_by_period[period_key] = {
                metric_key: 0
                for metric_key in metric_keys
            }

        for metric_key in metric_keys:
            totals_by_period[period_key][metric_key] += int(
                row["metrics"].get(metric_key) or 0
            )

    return totals_by_period


def build_weekly_closing_section(
    *,
    target_month: Any,
) -> dict[str, Any]:
    year, month, normalized_target_month = _ensure_target_month(target_month)

    week_ranges = _iter_month_week_ranges(year=year, month=month)

    warnings: list[dict[str, Any]] = []
    periods: list[dict[str, Any]] = []
    data: list[dict[str, Any]] = []

    for period in week_ranges:
        snapshot = _resolve_last_canonical_snapshot_for_date_range(
            start_date=period["date_from"],
            end_date=period["date_to"],
        )

        periods.append(
            _build_weekly_period_payload(
                period=period,
                snapshot=snapshot,
            )
        )

        if snapshot is None:
            warnings.append(
                {
                    "code": "no_canonical_snapshot_for_week",
                    "message": "No existe snapshot canónico KPI Desempeño para la semana solicitada.",
                    "target_month": normalized_target_month,
                    "period_key": period["period_key"],
                    "date_from": period["date_from"].isoformat(),
                    "date_to": period["date_to"].isoformat(),
                }
            )
            continue

        raw_rows = _fetch_snapshot_rows(snapshot_id=snapshot.id)
        rows = [
            row
            for row in raw_rows
            if not _is_out_of_scope_raw_branch(_normalize_raw_branch_name(row.sucursal))
        ]

        canon_by_row_id, alias_warnings = _resolve_rows_branch_canon(rows=rows)
        warnings.extend(alias_warnings)

        sucursales_canon = {
            sucursal_canon
            for sucursal_canon in canon_by_row_id.values()
            if sucursal_canon
        }

        branch_catalog_by_canon = _fetch_branch_catalog_by_canon(
            sucursales_canon=sucursales_canon,
        )

        data.extend(
            _build_weekly_row_payload(
                row=row,
                snapshot=snapshot,
                period=period,
                sucursal_canon=canon_by_row_id.get(row.id),
                branch_catalog_by_canon=branch_catalog_by_canon,
            )
            for row in rows
        )

    sorted_data = _sort_weekly_rows(data)

    return {
        "key": "weekly_closing",
        "title": "Cierre semanal de socios",
        "chart_type": "grouped_bar",
        "status": "ok" if data else "empty",
        "target_month": normalized_target_month,
        "rule": {
            "description": "Último snapshot canónico disponible dentro de cada bloque semanal del mes.",
            "report_type_key": KPI_DESEMPENO_REPORT_TYPE_KEY,
            "snapshot_kind": KPI_DESEMPENO_SNAPSHOT_KIND,
            "canonical_only": True,
            "metric": "socios_activos_del_mes",
            "week_definition": "Bloques fijos dentro del mes: 1-7, 8-14, 15-21, 22-28, 29-fin de mes.",
        },
        "periods": periods,
        "warnings": warnings,
        "totals_by_period": _build_weekly_totals(sorted_data),
        "data": sorted_data,
    }

def _add_months(
    *,
    year: int,
    month: int,
    months_to_add: int,
) -> tuple[int, int]:
    month_index = (year * 12) + (month - 1) + months_to_add
    new_year = month_index // 12
    new_month = (month_index % 12) + 1
    return new_year, new_month


def _ensure_history_granularity(value: Any) -> str:
    normalized = str(value or "quarterly").strip().lower()

    if normalized not in {
        "monthly",
        "bimonthly",
        "quarterly",
    }:
        raise KpiDesempenoQueryServiceError(
            "history_granularity debe ser monthly, bimonthly o quarterly."
        )

    return normalized


def _history_granularity_month_span(
    *,
    granularity: str,
) -> int:
    if granularity == "monthly":
        return 1

    if granularity == "bimonthly":
        return 2

    if granularity == "quarterly":
        return 3

    raise KpiDesempenoQueryServiceError(
        "Granularidad histórica no soportada."
    )


def _history_period_label(
    *,
    date_from: date,
    date_to: date,
    granularity: str,
) -> str:
    if granularity == "monthly":
        return f"{date_from.year:04d}-{date_from.month:02d}"

    if granularity == "bimonthly":
        return (
            f"{date_from.year:04d}-{date_from.month:02d}"
            f" a {date_to.year:04d}-{date_to.month:02d}"
        )

    if granularity == "quarterly":
        quarter = ((date_from.month - 1) // 3) + 1

        return f"{date_from.year:04d} T{quarter}"

    return f"{date_from.isoformat()} a {date_to.isoformat()}"


def _iter_history_period_ranges(
    *,
    start_month: Any,
    end_month: Any,
    granularity: str,
) -> list[dict[str, Any]]:
    start_year, start_month_number, normalized_start_month = _ensure_target_month(
        start_month
    )
    end_year, end_month_number, normalized_end_month = _ensure_target_month(
        end_month
    )

    start_date, _ = _month_bounds(
        year=start_year,
        month=start_month_number,
    )
    end_month_start, end_next_month_start = _month_bounds(
        year=end_year,
        month=end_month_number,
    )
    final_date = end_next_month_start - timedelta(days=1)

    if start_date > final_date:
        raise KpiDesempenoQueryServiceError(
            "start_month no puede ser mayor que end_month."
        )

    month_span = _history_granularity_month_span(granularity=granularity)

    periods: list[dict[str, Any]] = []
    period_number = 1
    current_year = start_year
    current_month = start_month_number

    while True:
        current_start, _ = _month_bounds(
            year=current_year,
            month=current_month,
        )

        if current_start > final_date:
            break

        next_year, next_month = _add_months(
            year=current_year,
            month=current_month,
            months_to_add=month_span,
        )
        next_period_start, _ = _month_bounds(
            year=next_year,
            month=next_month,
        )

        current_end = min(
            next_period_start - timedelta(days=1),
            final_date,
        )

        period_key = (
            f"{granularity.upper()}_{period_number:03d}_"
            f"{current_start.strftime('%Y%m')}_{current_end.strftime('%Y%m')}"
        )

        periods.append(
            {
                "period_key": period_key,
                "label": _history_period_label(
                    date_from=current_start,
                    date_to=current_end,
                    granularity=granularity,
                ),
                "date_from": current_start,
                "date_to": current_end,
                "granularity": granularity,
                "start_month": normalized_start_month,
                "end_month": normalized_end_month,
            }
        )

        period_number += 1
        current_year = next_year
        current_month = next_month

    return periods


def _build_historical_period_empty_payload(
    *,
    period: dict[str, Any],
) -> dict[str, Any]:
    return {
        "period_key": period["period_key"],
        "label": period["label"],
        "date_from": period["date_from"].isoformat(),
        "date_to": period["date_to"].isoformat(),
        "resolved_snapshot": None,
        "metrics": None,
        "source": None,
    }


def _build_historical_period_payload(
    *,
    period: dict[str, Any],
    snapshot: KpiDesempenoSnapshotORM,
) -> dict[str, Any]:
    raw_rows = _fetch_snapshot_rows(snapshot_id=snapshot.id)
    rows = [
        row
        for row in raw_rows
        if not _is_out_of_scope_raw_branch(_normalize_raw_branch_name(row.sucursal))
    ]

    socios_inicio = sum(
        int(row.socios_activos_inicio_mes or 0)
        for row in rows
    )
    socios_cierre = sum(
        int(row.socios_activos_del_mes or 0)
        for row in rows
    )
    clientes_nuevos = sum(
        int(row.clientes_nuevo_real or 0)
        for row in rows
    )
    reactivaciones = sum(
        int(row.reactivaciones or 0)
        for row in rows
    )
    bajas = sum(
        int(row.bajas or 0)
        for row in rows
    )

    crecimiento_real = socios_cierre - socios_inicio
    movimiento_reportado = clientes_nuevos + reactivaciones - bajas
    ajuste_no_explicado = crecimiento_real - movimiento_reportado

    return {
        "period_key": period["period_key"],
        "label": period["label"],
        "date_from": period["date_from"].isoformat(),
        "date_to": period["date_to"].isoformat(),
        "resolved_snapshot": {
            "snapshot_id": snapshot.id,
            "business_date": snapshot.business_date.isoformat(),
            "captured_at": (
                snapshot.captured_at.isoformat()
                if snapshot.captured_at
                else None
            ),
            "row_count_valid": snapshot.row_count_valid,
            "row_count_rejected": snapshot.row_count_rejected,
        },
        "metrics": {
            "socios_activos_inicio_periodo": socios_inicio,
            "socios_activos_cierre_periodo": socios_cierre,
            "clientes_nuevos_mtd_snapshot": clientes_nuevos,
            "reactivaciones_mtd_snapshot": reactivaciones,
            "bajas_mtd_snapshot": bajas,
            "crecimiento_real_snapshot": crecimiento_real,
            "movimiento_reportado_snapshot": movimiento_reportado,
            "ajuste_no_explicado_snapshot": ajuste_no_explicado,
        },
        "source": {
            "snapshot_id": snapshot.id,
            "business_date": snapshot.business_date.isoformat(),
            "report_type_key": snapshot.report_type_key,
            "snapshot_kind": snapshot.snapshot_kind,
            "is_canonical": snapshot.is_canonical,
        },
    }


def build_historical_closing_section(
    *,
    start_month: Any,
    end_month: Any,
    granularity: Any = "quarterly",
) -> dict[str, Any]:
    normalized_granularity = _ensure_history_granularity(granularity)

    periods = _iter_history_period_ranges(
        start_month=start_month,
        end_month=end_month,
        granularity=normalized_granularity,
    )

    warnings: list[dict[str, Any]] = []
    data: list[dict[str, Any]] = []

    for period in periods:
        snapshot = _resolve_last_canonical_snapshot_for_date_range(
            start_date=period["date_from"],
            end_date=period["date_to"],
        )

        if snapshot is None:
            warnings.append(
                {
                    "code": "no_canonical_snapshot_for_history_period",
                    "message": "No existe snapshot canónico KPI Desempeño para el periodo histórico solicitado.",
                    "period_key": period["period_key"],
                    "label": period["label"],
                    "date_from": period["date_from"].isoformat(),
                    "date_to": period["date_to"].isoformat(),
                    "granularity": normalized_granularity,
                }
            )
            data.append(
                _build_historical_period_empty_payload(period=period)
            )
            continue

        data.append(
            _build_historical_period_payload(
                period=period,
                snapshot=snapshot,
            )
        )

    resolved_periods_count = len(
        [
            item
            for item in data
            if item.get("resolved_snapshot") is not None
        ]
    )

    return {
        "key": "historical_closing",
        "title": "Histórico de socios",
        "chart_type": "line",
        "status": "ok" if resolved_periods_count > 0 else "empty",
        "start_month": str(start_month),
        "end_month": str(end_month),
        "granularity": normalized_granularity,
        "rule": {
            "description": "Último snapshot canónico disponible dentro de cada periodo histórico.",
            "report_type_key": KPI_DESEMPENO_REPORT_TYPE_KEY,
            "snapshot_kind": KPI_DESEMPENO_SNAPSHOT_KIND,
            "canonical_only": True,
            "metric": "socios_activos_del_mes",
            "available_granularities": [
                "monthly",
                "bimonthly",
                "quarterly",
            ],
        },
        "periods_count": len(periods),
        "resolved_periods_count": resolved_periods_count,
        "warnings": warnings,
        "data": data,
    }


def _iter_continuous_week_ranges(
    *,
    start_month: Any,
    end_month: Any,
) -> list[dict[str, Any]]:
    start_year, start_month_number, normalized_start_month = _ensure_target_month(
        start_month
    )
    end_year, end_month_number, normalized_end_month = _ensure_target_month(
        end_month
    )

    current_start, _ = _month_bounds(
        year=start_year,
        month=start_month_number,
    )
    _, end_next_month_start = _month_bounds(
        year=end_year,
        month=end_month_number,
    )
    final_date = end_next_month_start - timedelta(days=1)

    if current_start > final_date:
        raise KpiDesempenoQueryServiceError(
            "start_month no puede ser mayor que end_month."
        )

    periods: list[dict[str, Any]] = []
    week_number = 1

    while current_start <= final_date:
        current_end = min(
            current_start + timedelta(days=6),
            final_date,
        )

        period_key = (
            f"WEEK_{week_number:03d}_"
            f"{current_start.strftime('%Y%m%d')}_"
            f"{current_end.strftime('%Y%m%d')}"
        )

        periods.append(
            {
                "period_key": period_key,
                "label": _format_week_range_label(
                    start_date=current_start,
                    end_date=current_end,
                ),
                "date_from": current_start,
                "date_to": current_end,
                "start_month": normalized_start_month,
                "end_month": normalized_end_month,
                "week_number": week_number,
            }
        )

        week_number += 1
        current_start = current_end + timedelta(days=1)

    return periods


def _format_week_range_label(
    *,
    start_date: date,
    end_date: date,
) -> str:
    if start_date.year == end_date.year and start_date.month == end_date.month:
        return (
            f"{start_date.day} al {end_date.day} "
            f"{_spanish_month_name(start_date.month)} {start_date.year}"
        )

    return (
        f"{start_date.day} {_spanish_month_abbrev(start_date.month)} "
        f"al {end_date.day} {_spanish_month_abbrev(end_date.month)} "
        f"{end_date.year}"
    )


def _spanish_month_name(month: int) -> str:
    names = {
        1: "enero",
        2: "febrero",
        3: "marzo",
        4: "abril",
        5: "mayo",
        6: "junio",
        7: "julio",
        8: "agosto",
        9: "septiembre",
        10: "octubre",
        11: "noviembre",
        12: "diciembre",
    }

    return names.get(month, str(month))


def _spanish_month_abbrev(month: int) -> str:
    names = {
        1: "ene",
        2: "feb",
        3: "mar",
        4: "abr",
        5: "may",
        6: "jun",
        7: "jul",
        8: "ago",
        9: "sep",
        10: "oct",
        11: "nov",
        12: "dic",
    }

    return names.get(month, str(month))


def _is_excluded_weekly_branch_series_row(
    *,
    row: KpiDesempenoSnapshotRowORM,
    sucursal_canon: str | None,
    branch_catalog: TrackBranchCatalogORM | None,
) -> bool:
    raw_branch_name = _normalize_raw_branch_name(row.sucursal)
    normalized_raw = raw_branch_name.strip().upper()
    normalized_canon = str(sucursal_canon or "").strip().upper()

    if normalized_raw in {
        "BECA",
        "LA VIGA",
        "LA_VIGA",
    }:
        return True

    if normalized_canon in {
        "LA_VIGA",
    }:
        return True

    if branch_catalog is not None and branch_catalog.is_track_active is False:
        return True

    return False


def _build_weekly_branch_series_period_payload(
    *,
    period: dict[str, Any],
    snapshot: KpiDesempenoSnapshotORM | None,
) -> dict[str, Any]:
    return {
        "period_key": period["period_key"],
        "label": period["label"],
        "week_number": period["week_number"],
        "date_from": period["date_from"].isoformat(),
        "date_to": period["date_to"].isoformat(),
        "resolved_snapshot": (
            {
                "snapshot_id": snapshot.id,
                "business_date": snapshot.business_date.isoformat(),
                "captured_at": (
                    snapshot.captured_at.isoformat()
                    if snapshot.captured_at
                    else None
                ),
                "row_count_valid": snapshot.row_count_valid,
                "row_count_rejected": snapshot.row_count_rejected,
            }
            if snapshot is not None
            else None
        ),
    }


def build_weekly_branch_series_section(
    *,
    start_month: Any,
    end_month: Any,
) -> dict[str, Any]:
    periods = _iter_continuous_week_ranges(
        start_month=start_month,
        end_month=end_month,
    )

    warnings: list[dict[str, Any]] = []
    period_payloads: list[dict[str, Any]] = []
    data: list[dict[str, Any]] = []

    for period in periods:
        snapshot = _resolve_last_canonical_snapshot_for_date_range(
            start_date=period["date_from"],
            end_date=period["date_to"],
        )

        period_payloads.append(
            _build_weekly_branch_series_period_payload(
                period=period,
                snapshot=snapshot,
            )
        )

        if snapshot is None:
            warnings.append(
                {
                    "code": "no_canonical_snapshot_for_weekly_series_period",
                    "message": "No existe snapshot canónico KPI Desempeño para el periodo semanal solicitado.",
                    "period_key": period["period_key"],
                    "label": period["label"],
                    "date_from": period["date_from"].isoformat(),
                    "date_to": period["date_to"].isoformat(),
                }
            )
            continue

        raw_rows = _fetch_snapshot_rows(snapshot_id=snapshot.id)
        rows = [
            row
            for row in raw_rows
            if not _is_out_of_scope_raw_branch(_normalize_raw_branch_name(row.sucursal))
        ]

        canon_by_row_id, alias_warnings = _resolve_rows_branch_canon(rows=rows)
        warnings.extend(alias_warnings)

        sucursales_canon = {
            sucursal_canon
            for sucursal_canon in canon_by_row_id.values()
            if sucursal_canon
        }

        branch_catalog_by_canon = _fetch_branch_catalog_by_canon(
            sucursales_canon=sucursales_canon,
        )

        capacity_by_canon = _fetch_branch_capacity_targets_by_canon(
            sucursales_canon=sucursales_canon,
            target_month=end_month,
        )

        for row in rows:
            sucursal_canon = canon_by_row_id.get(row.id)
            branch_catalog = (
                branch_catalog_by_canon.get(sucursal_canon)
                if sucursal_canon
                else None
            )

            if _is_excluded_weekly_branch_series_row(
                row=row,
                sucursal_canon=sucursal_canon,
                branch_catalog=branch_catalog,
            ):
                continue

            socios_cierre = int(row.socios_activos_del_mes or 0)

            if socios_cierre <= 0:
                continue

            data.append(
                {
                    "period": {
                        "period_key": period["period_key"],
                        "label": period["label"],
                        "week_number": period["week_number"],
                        "date_from": period["date_from"].isoformat(),
                        "date_to": period["date_to"].isoformat(),
                    },
                    "branch": _build_branch_payload(
                        row=row,
                        sucursal_canon=sucursal_canon,
                        branch_catalog_by_canon=branch_catalog_by_canon,
                        capacity_by_canon=capacity_by_canon,
                    ),
                    "metrics": {
                        "socios_activos_cierre_semana": socios_cierre,
                        "socios_activos_inicio_mes": int(row.socios_activos_inicio_mes or 0),
                        "clientes_nuevos_mtd": int(row.clientes_nuevo_real or 0),
                        "reactivaciones_mtd": int(row.reactivaciones or 0),
                        "bajas_mtd": int(row.bajas or 0),
                    },
                    "source": {
                        "snapshot_id": snapshot.id,
                        "business_date": snapshot.business_date.isoformat(),
                        "report_type_key": snapshot.report_type_key,
                        "snapshot_kind": snapshot.snapshot_kind,
                        "is_canonical": snapshot.is_canonical,
                    },
                }
            )

    data = sorted(
        data,
        key=lambda item: (
            item["branch"]["display_order"]
            if item["branch"]["display_order"] is not None
            else 999999,
            item["branch"]["track_label"] or "",
            item["period"]["week_number"],
        ),
    )

    return {
        "key": "weekly_branch_series",
        "title": "Crecimiento promedio semanal de socios",
        "chart_type": "grouped_bar",
        "status": "ok" if data else "empty",
        "start_month": str(start_month),
        "end_month": str(end_month),
        "rule": {
            "description": "Último snapshot canónico disponible dentro de cada bloque semanal continuo del rango histórico.",
            "report_type_key": KPI_DESEMPENO_REPORT_TYPE_KEY,
            "snapshot_kind": KPI_DESEMPENO_SNAPSHOT_KIND,
            "canonical_only": True,
            "metric": "socios_activos_del_mes",
            "week_definition": "Bloques continuos de 7 días iniciando el día 1 del start_month.",
        },
        "periods": period_payloads,
        "warnings": warnings,
        "data": data,
    }




