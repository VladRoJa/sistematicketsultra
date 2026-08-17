"""Inversión Meta canónica asignada al dashboard de Marketing.

La inversión se agrega primero por campaña. La evidencia iVentas sólo
resuelve la sucursal de cada campaña y nunca participa en la suma de spend.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

from sqlalchemy import select

from app.extensions import db
from app.models import (
    MarketingIventasContactORM,
    MarketingIventasContactTagORM,
    MarketingIventasSyncRunORM,
    MarketingMetaAdInsightORM,
    MarketingMetaSyncRunORM,
)
from app.services.marketing_iventas_service import TAG_KIND_META_AD


META_SYNC_STATUS_COMPLETED = "COMPLETED"


@dataclass(frozen=True)
class MetaDashboardInvestmentData:
    available: bool
    meta_sync_run_id: int | None
    iventas_sync_run_id: int | None
    date_from: date | None
    date_to: date | None
    total_meta_spend: Decimal | None
    assigned_spend: Decimal | None
    unassigned_spend: Decimal | None
    conflict_spend: Decimal | None
    branch_spend: Mapping[int, Decimal]
    campaigns_total: int | None
    campaigns_assigned: int | None
    campaigns_unassigned: int | None
    campaigns_conflict: int | None


def build_meta_month_period_key(month_date: date) -> str:
    if not isinstance(month_date, date):
        raise TypeError("month_date debe ser date.")
    return f"META-{month_date.year:04d}-{month_date.month:02d}"


def build_canonical_meta_run_statement(*, period_key: str):
    period_value = str(period_key or "").strip()
    if not period_value:
        raise ValueError("period_key Meta no puede estar vacío.")

    return (
        select(
            MarketingMetaSyncRunORM.id.label("sync_run_id"),
            MarketingMetaSyncRunORM.date_from,
            MarketingMetaSyncRunORM.date_to,
        )
        .where(
            MarketingMetaSyncRunORM.period_key == period_value,
            MarketingMetaSyncRunORM.status
            == META_SYNC_STATUS_COMPLETED,
            MarketingMetaSyncRunORM.is_canonical.is_(True),
        )
        .order_by(MarketingMetaSyncRunORM.id.desc())
        .limit(1)
    )


def build_meta_campaign_insights_statement(*, meta_sync_run_id: int):
    if meta_sync_run_id <= 0:
        raise ValueError("meta_sync_run_id debe ser positivo.")

    return (
        select(
            MarketingMetaAdInsightORM.campaign_id,
            MarketingMetaAdInsightORM.ad_id,
            MarketingMetaAdInsightORM.spend,
        )
        .where(
            MarketingMetaAdInsightORM.sync_run_id
            == meta_sync_run_id
        )
        .order_by(
            MarketingMetaAdInsightORM.campaign_id.asc(),
            MarketingMetaAdInsightORM.ad_id.asc(),
            MarketingMetaAdInsightORM.id.asc(),
        )
    )


def build_iventas_campaign_evidence_statement(
    *,
    iventas_sync_run_id: int,
    meta_ad_ids: Iterable[str],
):
    if iventas_sync_run_id <= 0:
        raise ValueError("iventas_sync_run_id debe ser positivo.")

    normalized_ad_ids = tuple(
        sorted(
            {
                str(ad_id).strip()
                for ad_id in meta_ad_ids
                if str(ad_id).strip()
            }
        )
    )
    if not normalized_ad_ids:
        raise ValueError("meta_ad_ids no puede estar vacío.")

    return (
        select(
            MarketingIventasContactTagORM.meta_ad_id,
            MarketingIventasContactORM.sucursal_id,
        )
        .select_from(MarketingIventasContactTagORM)
        .join(
            MarketingIventasContactORM,
            (
                MarketingIventasContactORM.id
                == MarketingIventasContactTagORM.iventas_contact_row_id
            )
            & (
                MarketingIventasContactORM.sync_run_id
                == MarketingIventasContactTagORM.sync_run_id
            ),
        )
        .where(
            MarketingIventasContactTagORM.sync_run_id
            == iventas_sync_run_id,
            MarketingIventasContactORM.sync_run_id
            == iventas_sync_run_id,
            MarketingIventasContactORM.first_message_at_utc.is_not(None),
            MarketingIventasContactTagORM.tag_kind == TAG_KIND_META_AD,
            MarketingIventasContactTagORM.meta_ad_id.is_not(None),
            MarketingIventasContactTagORM.meta_ad_id.in_(
                normalized_ad_ids
            ),
        )
        .distinct()
        .order_by(
            MarketingIventasContactTagORM.meta_ad_id.asc(),
            MarketingIventasContactORM.sucursal_id.asc(),
        )
    )


def _to_decimal(value: Any) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise RuntimeError("Meta contiene un spend inválido.") from exc
    if not result.is_finite() or result < 0:
        raise RuntimeError("Meta contiene un spend inválido.")
    return result


def _aggregate_campaign_investment(
    *,
    meta_sync_run_id: int,
    iventas_sync_run_id: int | None,
    date_from: date,
    date_to: date,
    insight_rows: Iterable[Mapping[str, Any]],
    evidence_rows: Iterable[Mapping[str, Any]],
) -> MetaDashboardInvestmentData:
    campaign_spend: dict[str, Decimal] = {}
    campaign_ad_ids: dict[str, set[str]] = {}

    for row in insight_rows:
        campaign_id = str(row["campaign_id"] or "").strip()
        ad_id = str(row["ad_id"] or "").strip()
        if not campaign_id or not ad_id:
            raise RuntimeError(
                "Meta contiene campaign_id o ad_id vacío."
            )
        campaign_spend[campaign_id] = (
            campaign_spend.get(campaign_id, Decimal("0"))
            + _to_decimal(row["spend"])
        )
        campaign_ad_ids.setdefault(campaign_id, set()).add(ad_id)

    branches_by_ad: dict[str, set[int]] = {}
    for row in evidence_rows:
        ad_id = str(row["meta_ad_id"] or "").strip()
        if not ad_id:
            continue
        branches_by_ad.setdefault(ad_id, set()).add(
            int(row["sucursal_id"])
        )

    assigned_spend = Decimal("0")
    unassigned_spend = Decimal("0")
    conflict_spend = Decimal("0")
    branch_spend: dict[int, Decimal] = {}
    campaigns_assigned = 0
    campaigns_unassigned = 0
    campaigns_conflict = 0

    for campaign_id, spend in campaign_spend.items():
        branch_ids: set[int] = set()
        for ad_id in campaign_ad_ids[campaign_id]:
            branch_ids.update(branches_by_ad.get(ad_id, set()))

        if len(branch_ids) == 1:
            branch_id = next(iter(branch_ids))
            branch_spend[branch_id] = (
                branch_spend.get(branch_id, Decimal("0")) + spend
            )
            assigned_spend += spend
            campaigns_assigned += 1
        elif not branch_ids:
            unassigned_spend += spend
            campaigns_unassigned += 1
        else:
            conflict_spend += spend
            campaigns_conflict += 1

    total_meta_spend = sum(
        campaign_spend.values(),
        Decimal("0"),
    )

    return MetaDashboardInvestmentData(
        available=True,
        meta_sync_run_id=meta_sync_run_id,
        iventas_sync_run_id=iventas_sync_run_id,
        date_from=date_from,
        date_to=date_to,
        total_meta_spend=total_meta_spend,
        assigned_spend=assigned_spend,
        unassigned_spend=unassigned_spend,
        conflict_spend=conflict_spend,
        branch_spend=branch_spend,
        campaigns_total=len(campaign_spend),
        campaigns_assigned=campaigns_assigned,
        campaigns_unassigned=campaigns_unassigned,
        campaigns_conflict=campaigns_conflict,
    )


def read_meta_dashboard_investment_data(
    *,
    month_date: date,
    iventas_sync_run_id: int | None,
    session: Any | None = None,
) -> MetaDashboardInvestmentData:
    if iventas_sync_run_id is not None and iventas_sync_run_id <= 0:
        raise ValueError("iventas_sync_run_id debe ser positivo.")

    session_value = session if session is not None else db.session
    canonical_run = (
        session_value.execute(
            build_canonical_meta_run_statement(
                period_key=build_meta_month_period_key(month_date)
            )
        )
        .mappings()
        .first()
    )

    if canonical_run is None:
        return MetaDashboardInvestmentData(
            available=False,
            meta_sync_run_id=None,
            iventas_sync_run_id=iventas_sync_run_id,
            date_from=None,
            date_to=None,
            total_meta_spend=None,
            assigned_spend=None,
            unassigned_spend=None,
            conflict_spend=None,
            branch_spend={},
            campaigns_total=None,
            campaigns_assigned=None,
            campaigns_unassigned=None,
            campaigns_conflict=None,
        )

    meta_sync_run_id = int(canonical_run["sync_run_id"])
    insights = (
        session_value.execute(
            build_meta_campaign_insights_statement(
                meta_sync_run_id=meta_sync_run_id
            )
        )
        .mappings()
        .all()
    )
    meta_ad_ids = {
        str(row["ad_id"]).strip()
        for row in insights
        if str(row["ad_id"] or "").strip()
    }

    iventas_window_matches = False

    if iventas_sync_run_id is not None:
        iventas_run = session_value.get(
            MarketingIventasSyncRunORM,
            iventas_sync_run_id,
        )
        if iventas_run is None:
            raise RuntimeError(
                "El sync run iVentas solicitado ya no existe."
            )

        iventas_window_matches = (
            iventas_run.date_from == canonical_run["date_from"]
            and iventas_run.date_to == canonical_run["date_to"]
        )

    evidence: Iterable[Mapping[str, Any]] = ()
    if (
        iventas_sync_run_id is not None
        and iventas_window_matches
        and meta_ad_ids
    ):
        evidence = (
            session_value.execute(
                build_iventas_campaign_evidence_statement(
                    iventas_sync_run_id=iventas_sync_run_id,
                    meta_ad_ids=meta_ad_ids,
                )
            )
            .mappings()
            .all()
        )

    result = _aggregate_campaign_investment(
        meta_sync_run_id=meta_sync_run_id,
        iventas_sync_run_id=iventas_sync_run_id,
        date_from=canonical_run["date_from"],
        date_to=canonical_run["date_to"],
        insight_rows=insights,
        evidence_rows=evidence,
    )

    if (
        iventas_sync_run_id is None
        or not iventas_window_matches
    ):
        return MetaDashboardInvestmentData(
            available=True,
            meta_sync_run_id=result.meta_sync_run_id,
            iventas_sync_run_id=iventas_sync_run_id,
            date_from=result.date_from,
            date_to=result.date_to,
            total_meta_spend=result.total_meta_spend,
            assigned_spend=None,
            unassigned_spend=None,
            conflict_spend=None,
            branch_spend={},
            campaigns_total=result.campaigns_total,
            campaigns_assigned=None,
            campaigns_unassigned=None,
            campaigns_conflict=None,
        )

    return result
