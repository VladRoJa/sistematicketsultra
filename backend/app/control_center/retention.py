from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from app.control_center.access import ControlScope
from app.models.warehouse import TrackBranchCatalogORM, TrackDailyMartORM
from app.warehouse.services.track_daily_query_version_service import (
    resolve_effective_track_daily_version,
)


@dataclass(frozen=True)
class RetentionBranchRow:
    sucursal_id: int | None
    sucursal_canon: str
    sucursal: str
    bajas_reales_mtd: int | None
    meta_bajas_mes: int | None

    def to_public_dict(self) -> dict[str, Any]:
        usage = _ratio(self.bajas_reales_mtd, self.meta_bajas_mes)
        remaining = None
        if self.bajas_reales_mtd is not None and self.meta_bajas_mes is not None:
            remaining = self.meta_bajas_mes - self.bajas_reales_mtd

        return {
            "sucursal_id": self.sucursal_id,
            "sucursal_canon": self.sucursal_canon,
            "sucursal": self.sucursal,
            "bajas_reales_mtd": self.bajas_reales_mtd,
            "meta_bajas_mes": self.meta_bajas_mes,
            "limit_usage_ratio": usage,
            "remaining_margin": remaining,
        }


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _ratio(numerator: int | None, denominator: int | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return float(Decimal(numerator) / Decimal(denominator))


def _aggregate_rows(rows: list[RetentionBranchRow]) -> dict[str, Any]:
    actual_values = [
        row.bajas_reales_mtd
        for row in rows
        if row.bajas_reales_mtd is not None
    ]
    target_values = [
        row.meta_bajas_mes
        for row in rows
        if row.meta_bajas_mes is not None
    ]

    actual = sum(actual_values) if actual_values else None
    target = sum(target_values) if target_values else None
    usage = _ratio(actual, target)
    remaining = None
    if actual is not None and target is not None:
        remaining = target - actual

    return {
        "bajas_reales_mtd": actual,
        "meta_bajas_mes": target,
        "limit_usage_ratio": usage,
        "remaining_margin": remaining,
        "branch_count": len(rows),
        "actual_coverage_branch_count": len(actual_values),
        "target_coverage_branch_count": len(target_values),
    }


def _branch_catalog_by_canon() -> dict[str, TrackBranchCatalogORM]:
    rows = TrackBranchCatalogORM.query.all()
    return {
        str(row.sucursal_canon): row
        for row in rows
        if str(row.sucursal_canon or "").strip()
    }


def build_retention_summary(
    *,
    cutoff_date: date,
    effective_scope: ControlScope,
    generation_mode: str = "manual_preview",
) -> dict[str, Any]:
    resolved_version = resolve_effective_track_daily_version(
        track_date=cutoff_date,
        generation_mode=generation_mode,
    )

    if resolved_version is None:
        return {
            "status": "ok",
            "cutoff_date": cutoff_date.isoformat(),
            "generation_mode": generation_mode,
            "resolved_version": None,
            "summary": _aggregate_rows([]),
            "branches": [],
        }

    catalog_by_canon = _branch_catalog_by_canon()
    query = TrackDailyMartORM.query.filter_by(
        track_daily_version_id=resolved_version.id,
    )

    if effective_scope.type != "GLOBAL":
        allowed_branch_ids = set(effective_scope.branch_ids)
        allowed_canons = [
            canon
            for canon, catalog in catalog_by_canon.items()
            if catalog.sucursal_id is not None
            and int(catalog.sucursal_id) in allowed_branch_ids
        ]

        if not allowed_canons:
            mart_rows = []
        else:
            mart_rows = query.filter(
                TrackDailyMartORM.sucursal_canon.in_(allowed_canons)
            ).all()
    else:
        mart_rows = query.all()

    rows: list[RetentionBranchRow] = []
    for mart_row in mart_rows:
        canon = str(mart_row.sucursal_canon or "").strip()
        catalog = catalog_by_canon.get(canon)
        branch_id = (
            int(catalog.sucursal_id)
            if catalog is not None and catalog.sucursal_id is not None
            else None
        )
        label = str(
            getattr(catalog, "track_label", None)
            or canon
            or "Sin sucursal"
        )

        rows.append(
            RetentionBranchRow(
                sucursal_id=branch_id,
                sucursal_canon=canon,
                sucursal=label,
                bajas_reales_mtd=_as_int(mart_row.bajas_reales_mtd),
                meta_bajas_mes=_as_int(mart_row.meta_bajas_mes),
            )
        )

    rows.sort(
        key=lambda row: (
            -(
                _ratio(row.bajas_reales_mtd, row.meta_bajas_mes)
                if _ratio(row.bajas_reales_mtd, row.meta_bajas_mes) is not None
                else -1.0
            ),
            row.sucursal.casefold(),
        )
    )

    return {
        "status": "ok",
        "cutoff_date": cutoff_date.isoformat(),
        "generation_mode": generation_mode,
        "resolved_version": {
            "id": resolved_version.id,
            "version_type": resolved_version.version_type,
            "status": resolved_version.status,
        },
        "summary": _aggregate_rows(rows),
        "branches": [row.to_public_dict() for row in rows],
    }
