#    backend\app\track_alerts\services\track_alert_region_rules_service.py


from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from app.extensions import db
from app.models.suite_governance import (
    SuiteRegionORM,
    SuiteSucursalRegionAssignmentORM,
)
from app.models.warehouse import (
    TrackBranchCatalogORM,
    TrackDailyMartORM,
)


@dataclass(frozen=True)
class TrackRegionRankingItem:
    region_key: str
    region_label: str
    ranking_position: int
    total_regions: int
    ingreso_real_total_mtd: Decimal
    meta_faycgo_mes: Decimal
    clientes_nuevos_real_mtd: int
    total_branches: int
    cumplimiento_ingreso_pct: Decimal | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "region_key": self.region_key,
            "region_label": self.region_label,
            "ranking_position": self.ranking_position,
            "total_regions": self.total_regions,
            "ingreso_real_total_mtd": str(self.ingreso_real_total_mtd),
            "meta_faycgo_mes": str(self.meta_faycgo_mes),
            "clientes_nuevos_real_mtd": self.clientes_nuevos_real_mtd,
            "total_branches": self.total_branches,
            "cumplimiento_ingreso_pct": (
                str(self.cumplimiento_ingreso_pct)
                if self.cumplimiento_ingreso_pct is not None
                else None
            ),
        }

@dataclass(frozen=True)
class TrackRegionBranchDetailItem:
    sucursal_id: int | None
    sucursal_canon: str
    sucursal_name: str
    orden_apertura: int | None
    ingreso_real_total_mtd: Decimal
    meta_faycgo_mes: Decimal
    clientes_nuevos_real_mtd: int
    cumplimiento_ingreso_pct: Decimal | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sucursal_id": self.sucursal_id,
            "sucursal_canon": self.sucursal_canon,
            "sucursal_name": self.sucursal_name,
            "orden_apertura": self.orden_apertura,
            "ingreso_real_total_mtd": str(self.ingreso_real_total_mtd),
            "meta_faycgo_mes": str(self.meta_faycgo_mes),
            "clientes_nuevos_real_mtd": self.clientes_nuevos_real_mtd,
            "cumplimiento_ingreso_pct": (
                str(self.cumplimiento_ingreso_pct)
                if self.cumplimiento_ingreso_pct is not None
                else None
            ),
        }


@dataclass(frozen=True)
class TrackRegionDetailItem:
    region_key: str
    region_label: str
    summary: TrackRegionRankingItem
    branches: list[TrackRegionBranchDetailItem]

    def to_dict(self) -> dict[str, Any]:
        return {
            "region_key": self.region_key,
            "region_label": self.region_label,
            "summary": self.summary.to_dict(),
            "branches": [
                branch.to_dict()
                for branch in self.branches
            ],
        }

def evaluate_regional_rankings(
    track_date: date,
    generation_mode: str = "manual_preview",
) -> dict[str, list[TrackRegionRankingItem]]:
    joined_rows = _load_track_rows_with_region(
        track_date=track_date,
        generation_mode=generation_mode,
    )

    region_totals = _build_region_totals(joined_rows)

    income_ranking = _rank_regions_by_decimal_metric(
        region_totals=region_totals,
        metric_key="ingreso_real_total_mtd",
    )

    income_compliance_ranking = _rank_regions_by_income_compliance(
        region_totals=region_totals,
    )

    new_clients_ranking = _rank_regions_by_integer_metric(
        region_totals=region_totals,
        metric_key="clientes_nuevos_real_mtd",
    )

    return {
        "income_ranking": income_ranking,
        "income_compliance_ranking": income_compliance_ranking,
        "new_clients_ranking": new_clients_ranking,
    }

def get_regional_detail(
    track_date: date,
    generation_mode: str = "manual_preview",
) -> dict[str, Any]:
    rankings = evaluate_regional_rankings(
        track_date=track_date,
        generation_mode=generation_mode,
    )

    joined_rows = _load_track_rows_with_region(
        track_date=track_date,
        generation_mode=generation_mode,
    )

    region_totals = _build_region_totals(joined_rows)

    summary_by_region = {
        item.region_key: item
        for item in _build_ranking_items(
            sorted(
                region_totals.values(),
                key=lambda item: item["region_label"],
            )
        )
    }

    income_compliance_position_by_region = _build_position_map(
        rankings["income_compliance_ranking"]
    )
    income_position_by_region = _build_position_map(
        rankings["income_ranking"]
    )
    new_clients_position_by_region = _build_position_map(
        rankings["new_clients_ranking"]
    )
    branches_by_region: dict[str, list[TrackRegionBranchDetailItem]] = {}

    for mart_row, branch_row, region_row in joined_rows:
        if not _has_faycgo_target(mart_row):
            continue

        region_key = region_row.region_key

        if region_key not in branches_by_region:
            branches_by_region[region_key] = []

        ingreso = _get_income_value(mart_row)
        meta = Decimal(mart_row.meta_faycgo_mes or 0)
        cumplimiento = None

        if meta > 0:
            cumplimiento = (ingreso / meta) * Decimal("100")

        sucursal = getattr(branch_row, "sucursal", None)
        sucursal_name = _get_branch_display_name(branch_row)

        orden_apertura = None

        if sucursal is not None:
            orden_apertura = getattr(sucursal, "orden_apertura", None)

        branches_by_region[region_key].append(
            TrackRegionBranchDetailItem(
                sucursal_id=branch_row.sucursal_id,
                sucursal_canon=branch_row.sucursal_canon,
                sucursal_name=sucursal_name,
                orden_apertura=orden_apertura,
                ingreso_real_total_mtd=ingreso,
                meta_faycgo_mes=meta,
                clientes_nuevos_real_mtd=int(
                    mart_row.clientes_nuevos_real_mtd or 0
                ),
                cumplimiento_ingreso_pct=cumplimiento,
            )
        )

    regions: list[TrackRegionDetailItem] = []

    for region_key, summary in summary_by_region.items():
        branches = sorted(
            branches_by_region.get(region_key, []),
            key=lambda item: (
                item.orden_apertura or 9999,
                item.sucursal_name,
            ),
        )

        regions.append(
            TrackRegionDetailItem(
                region_key=summary.region_key,
                region_label=summary.region_label,
                summary=summary,
                branches=branches,
            )
        )

    regions = sorted(
        regions,
        key=lambda item: item.region_label,
    )

    return {
        "track_date": track_date.isoformat(),
        "generation_mode": generation_mode,
        "rankings": {
            "income_compliance": [
                item.to_dict()
                for item in rankings["income_compliance_ranking"]
            ],
            "income": [
                item.to_dict()
                for item in rankings["income_ranking"]
            ],
            "new_clients": [
                item.to_dict()
                for item in rankings["new_clients_ranking"]
            ],
        },
        "regions": [
            _region_detail_to_dict(
                region=region,
                income_compliance_position_by_region=income_compliance_position_by_region,
                income_position_by_region=income_position_by_region,
                new_clients_position_by_region=new_clients_position_by_region,
            )
            for region in regions
        ],
        "business_rules": _get_regional_business_rules(),
    }

def _load_track_rows_with_region(
    track_date: date,
    generation_mode: str,
) -> list[tuple[TrackDailyMartORM, TrackBranchCatalogORM, SuiteRegionORM]]:
    return (
        db.session.query(
            TrackDailyMartORM,
            TrackBranchCatalogORM,
            SuiteRegionORM,
        )
        .join(
            TrackBranchCatalogORM,
            TrackBranchCatalogORM.sucursal_canon == TrackDailyMartORM.sucursal_canon,
        )
        .join(
            SuiteSucursalRegionAssignmentORM,
            SuiteSucursalRegionAssignmentORM.sucursal_id == TrackBranchCatalogORM.sucursal_id,
        )
        .join(
            SuiteRegionORM,
            SuiteRegionORM.id == SuiteSucursalRegionAssignmentORM.region_id,
        )
        .filter(
            TrackDailyMartORM.track_date == track_date,
            TrackDailyMartORM.generation_mode == generation_mode,
            SuiteSucursalRegionAssignmentORM.is_current.is_(True),
            SuiteRegionORM.is_active.is_(True),
            TrackBranchCatalogORM.is_track_active.is_(True),
        )
        .all()
    )


def _build_region_totals(
    joined_rows: list[tuple[TrackDailyMartORM, TrackBranchCatalogORM, SuiteRegionORM]],
) -> dict[str, dict[str, Any]]:
    region_totals: dict[str, dict[str, Any]] = {}

    for mart_row, branch_row, region_row in joined_rows:
        if not _has_faycgo_target(mart_row):
            continue

        region_key = region_row.region_key

        if region_key not in region_totals:
            region_totals[region_key] = {
                "region_key": region_row.region_key,
                "region_label": region_row.region_label,
                "ingreso_real_total_mtd": Decimal("0"),
                "meta_faycgo_mes": Decimal("0"),
                "clientes_nuevos_real_mtd": 0,
                "sucursales": set(),
            }

        region_totals[region_key]["ingreso_real_total_mtd"] += _get_income_value(
            mart_row
        )
        region_totals[region_key]["meta_faycgo_mes"] += Decimal(
            mart_row.meta_faycgo_mes or 0
        )
        region_totals[region_key]["clientes_nuevos_real_mtd"] += int(
            mart_row.clientes_nuevos_real_mtd or 0
        )
        region_totals[region_key]["sucursales"].add(branch_row.sucursal_id)

    return region_totals


def _rank_regions_by_decimal_metric(
    region_totals: dict[str, dict[str, Any]],
    metric_key: str,
) -> list[TrackRegionRankingItem]:
    ranked = sorted(
        region_totals.values(),
        key=lambda item: item[metric_key],
        reverse=True,
    )

    return _build_ranking_items(ranked)


def _rank_regions_by_integer_metric(
    region_totals: dict[str, dict[str, Any]],
    metric_key: str,
) -> list[TrackRegionRankingItem]:
    ranked = sorted(
        region_totals.values(),
        key=lambda item: item[metric_key],
        reverse=True,
    )

    return _build_ranking_items(ranked)

def _rank_regions_by_income_compliance(
    region_totals: dict[str, dict[str, Any]],
) -> list[TrackRegionRankingItem]:
    ranked = sorted(
        region_totals.values(),
        key=_get_income_compliance_pct,
        reverse=True,
    )

    return _build_ranking_items(ranked)


def _get_income_compliance_pct(
    region_total: dict[str, Any],
) -> Decimal:
    meta = region_total["meta_faycgo_mes"]
    ingreso = region_total["ingreso_real_total_mtd"]

    if meta <= 0:
        return Decimal("0")

    return (ingreso / meta) * Decimal("100")

def _build_ranking_items(
    ranked_region_totals: list[dict[str, Any]],
) -> list[TrackRegionRankingItem]:
    total_regions = len(ranked_region_totals)
    items: list[TrackRegionRankingItem] = []

    for index, region_total in enumerate(ranked_region_totals, start=1):
        meta = region_total["meta_faycgo_mes"]
        ingreso = region_total["ingreso_real_total_mtd"]

        cumplimiento = None

        if meta > 0:
            cumplimiento = (ingreso / meta) * Decimal("100")

        items.append(
            TrackRegionRankingItem(
                region_key=region_total["region_key"],
                region_label=region_total["region_label"],
                ranking_position=index,
                total_regions=total_regions,
                ingreso_real_total_mtd=ingreso,
                meta_faycgo_mes=meta,
                clientes_nuevos_real_mtd=region_total["clientes_nuevos_real_mtd"],
                total_branches=len(region_total["sucursales"]),
                cumplimiento_ingreso_pct=cumplimiento,
            )
        )

    return items


def _has_faycgo_target(row: TrackDailyMartORM) -> bool:
    return Decimal(row.meta_faycgo_mes or 0) > 0


def _get_income_value(row: TrackDailyMartORM) -> Decimal:
    value = row.ingreso_real_total_mtd

    if value is None:
        value = row.ingreso_real_mtd

    return Decimal(value or 0)

def _get_branch_display_name(
    branch_row: TrackBranchCatalogORM,
) -> str:
    sucursal = getattr(branch_row, "sucursal", None)

    if sucursal is not None:
        sucursal_name = getattr(sucursal, "sucursal", None)

        if sucursal_name:
            return str(sucursal_name).strip()

    if branch_row.track_label:
        return str(branch_row.track_label).replace("_", " ").strip().title()

    return str(branch_row.sucursal_canon).replace("_", " ").strip().title()


def _get_regional_business_rules() -> list[dict[str, str]]:
    return [
        {
            "key": "eligible_branches",
            "label": "Sucursales participantes",
            "description": "Solo participan sucursales con meta FAYCGO mensual mayor a 0.",
        },
        {
            "key": "region_source",
            "label": "Origen de regiones",
            "description": "Las regiones se toman desde suite_regions y suite_sucursal_region_assignments.",
        },
        {
            "key": "income_metric",
            "label": "Ingreso real total",
            "description": "El ingreso real acumulado usa ingreso_real_total_mtd, que integra ingreso base y agregadoras cuando existan.",
        },
        {
            "key": "income_compliance",
            "label": "Cumplimiento contra meta",
            "description": "Se calcula como ingreso real acumulado / meta FAYCGO mensual × 100.",
        },
        {
            "key": "compliance_ranking",
            "label": "Ranking por cumplimiento",
            "description": "Compara eficiencia contra meta, no tamaño de región.",
        },
        {
            "key": "income_ranking",
            "label": "Ranking por ingreso",
            "description": "Compara volumen total acumulado por región.",
        },
        {
            "key": "new_clients_ranking",
            "label": "Ranking por clientes nuevos",
            "description": "Compara captación total acumulada por región.",
        },
    ]
    
def _build_position_map(
    ranking_items: list[TrackRegionRankingItem],
) -> dict[str, int]:
    return {
        item.region_key: item.ranking_position
        for item in ranking_items
    }


def _region_detail_to_dict(
    *,
    region: TrackRegionDetailItem,
    income_compliance_position_by_region: dict[str, int],
    income_position_by_region: dict[str, int],
    new_clients_position_by_region: dict[str, int],
) -> dict[str, Any]:
    data = region.to_dict()

    summary = data.get("summary") or {}

    # En el detalle regional no usamos un ranking genérico,
    # porque cada región tiene posiciones distintas por métrica.
    summary.pop("ranking_position", None)

    data["summary"] = summary

    data["rankings"] = {
        "income_compliance_position": income_compliance_position_by_region.get(
            region.region_key
        ),
        "income_position": income_position_by_region.get(
            region.region_key
        ),
        "new_clients_position": new_clients_position_by_region.get(
            region.region_key
        ),
        "total_regions": region.summary.total_regions,
    }

    return data