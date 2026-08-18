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
ASSIGNMENT_STATUS_ASSIGNED = "ASSIGNED"
ASSIGNMENT_STATUS_UNASSIGNED = "UNASSIGNED"
ASSIGNMENT_STATUS_CONFLICT = "CONFLICT"


@dataclass(frozen=True)
class MetaDashboardCampaignData:
    campaign_id: str
    campaign_name: str | None
    account_id: str | None
    account_name: str | None
    spend: Decimal
    ads_count: int
    matched_ads_count: int
    meta_observed_leads: int
    assignment_status: str
    sucursal_id: int | None
    evidence_branch_ids: tuple[int, ...]
    impressions: int
    clicks: int


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
    campaign_rows: tuple[MetaDashboardCampaignData, ...]


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
            MarketingMetaAdInsightORM.account_id,
            MarketingMetaAdInsightORM.account_name,
            MarketingMetaAdInsightORM.campaign_id,
            MarketingMetaAdInsightORM.campaign_name,
            MarketingMetaAdInsightORM.ad_id,
            MarketingMetaAdInsightORM.spend,
            MarketingMetaAdInsightORM.impressions,
            MarketingMetaAdInsightORM.clicks,
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
            MarketingIventasContactORM.id.label(
                "iventas_contact_row_id"
            ),
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


def _optional_text(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


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
    campaign_names: dict[str, set[str]] = {}
    campaign_account_ids: dict[str, set[str]] = {}
    campaign_account_names: dict[str, set[str]] = {}
    campaign_impressions: dict[str, int] = {}
    campaign_clicks: dict[str, int] = {}

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
        optional_values = (
            (campaign_names, row.get("campaign_name")),
            (campaign_account_ids, row.get("account_id")),
            (campaign_account_names, row.get("account_name")),
        )
        for target, value in optional_values:
            normalized = _optional_text(value)
            if normalized is not None:
                target.setdefault(campaign_id, set()).add(normalized)
        campaign_impressions[campaign_id] = (
            campaign_impressions.get(campaign_id, 0)
            + int(row.get("impressions") or 0)
        )
        campaign_clicks[campaign_id] = (
            campaign_clicks.get(campaign_id, 0)
            + int(row.get("clicks") or 0)
        )

    branches_by_ad: dict[str, set[int]] = {}
    contacts_by_ad: dict[str, set[int]] = {}
    for row in evidence_rows:
        ad_id = str(row["meta_ad_id"] or "").strip()
        if not ad_id:
            continue
        branches_by_ad.setdefault(ad_id, set()).add(
            int(row["sucursal_id"])
        )
        contacts_by_ad.setdefault(ad_id, set()).add(
            int(row["iventas_contact_row_id"])
        )

    assigned_spend = Decimal("0")
    unassigned_spend = Decimal("0")
    conflict_spend = Decimal("0")
    branch_spend: dict[int, Decimal] = {}
    campaigns_assigned = 0
    campaigns_unassigned = 0
    campaigns_conflict = 0
    campaign_rows: list[MetaDashboardCampaignData] = []

    for campaign_id in sorted(campaign_spend):
        spend = campaign_spend[campaign_id]
        branch_ids: set[int] = set()
        contact_ids: set[int] = set()
        for ad_id in campaign_ad_ids[campaign_id]:
            branch_ids.update(branches_by_ad.get(ad_id, set()))
            contact_ids.update(contacts_by_ad.get(ad_id, set()))

        if len(branch_ids) == 1:
            branch_id = next(iter(branch_ids))
            branch_spend[branch_id] = (
                branch_spend.get(branch_id, Decimal("0")) + spend
            )
            assigned_spend += spend
            campaigns_assigned += 1
            assignment_status = ASSIGNMENT_STATUS_ASSIGNED
        elif not branch_ids:
            branch_id = None
            unassigned_spend += spend
            campaigns_unassigned += 1
            assignment_status = ASSIGNMENT_STATUS_UNASSIGNED
        else:
            branch_id = None
            conflict_spend += spend
            campaigns_conflict += 1
            assignment_status = ASSIGNMENT_STATUS_CONFLICT

        def first_value(
            values_by_campaign: Mapping[str, set[str]],
        ) -> str | None:
            values = values_by_campaign.get(campaign_id, set())
            return sorted(values)[0] if values else None

        campaign_rows.append(
            MetaDashboardCampaignData(
                campaign_id=campaign_id,
                campaign_name=first_value(campaign_names),
                account_id=first_value(campaign_account_ids),
                account_name=first_value(campaign_account_names),
                spend=spend,
                ads_count=len(campaign_ad_ids[campaign_id]),
                matched_ads_count=sum(
                    1
                    for ad_id in campaign_ad_ids[campaign_id]
                    if branches_by_ad.get(ad_id)
                ),
                meta_observed_leads=len(contact_ids),
                assignment_status=assignment_status,
                sucursal_id=branch_id,
                evidence_branch_ids=tuple(sorted(branch_ids)),
                impressions=campaign_impressions.get(
                    campaign_id,
                    0,
                ),
                clicks=campaign_clicks.get(campaign_id, 0),
            )
        )

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
        campaign_rows=tuple(campaign_rows),
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
            campaign_rows=(),
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
            campaign_rows=(),
        )

    return result


def serialize_meta_investment_detail(
    *,
    month: str,
    scope: Mapping[str, Any],
    sucursal_id: int | None,
    meta_data: MetaDashboardInvestmentData,
    selected_branch_ids: Iterable[int],
    branch_names: Mapping[int, str],
    expose_global_totals: bool,
) -> dict[str, Any]:
    selected_ids = set(selected_branch_ids)
    assignment_available = (
        meta_data.available
        and meta_data.assigned_spend is not None
    )

    rows = [
        row
        for row in meta_data.campaign_rows
        if (
            expose_global_totals
            or (
                row.assignment_status
                == ASSIGNMENT_STATUS_ASSIGNED
                and row.sucursal_id in selected_ids
            )
        )
    ]
    card_investment = (
        sum(
            (
                row.spend
                for row in rows
                if row.assignment_status
                == ASSIGNMENT_STATUS_ASSIGNED
            ),
            Decimal("0"),
        )
        if assignment_available
        else None
    )

    def global_decimal(value: Decimal | None) -> float | None:
        if not expose_global_totals or value is None:
            return None
        return float(value)

    def global_count(value: int | None) -> int | None:
        return value if expose_global_totals else None

    return {
        "month": month,
        "scope": dict(scope),
        "filters": {
            "sucursal_id": sucursal_id,
        },
        "summary": {
            "card_investment": (
                float(card_investment)
                if card_investment is not None
                else None
            ),
            "total_meta_spend": global_decimal(
                meta_data.total_meta_spend
            ),
            "assigned_spend": (
                float(card_investment)
                if card_investment is not None
                else None
            ),
            "unassigned_spend": global_decimal(
                meta_data.unassigned_spend
            ),
            "conflict_spend": global_decimal(
                meta_data.conflict_spend
            ),
            "campaigns_total": (
                global_count(meta_data.campaigns_total)
                if expose_global_totals
                else len(rows)
            ),
            "campaigns_assigned": (
                global_count(meta_data.campaigns_assigned)
                if expose_global_totals
                else len(rows)
            ),
            "campaigns_unassigned": global_count(
                meta_data.campaigns_unassigned
            ),
            "campaigns_conflict": global_count(
                meta_data.campaigns_conflict
            ),
        },
        "source": {
            "available": meta_data.available,
            "assignment_available": assignment_available,
            "meta_sync_run_id": meta_data.meta_sync_run_id,
            "iventas_sync_run_id": meta_data.iventas_sync_run_id,
            "date_from": (
                meta_data.date_from.isoformat()
                if meta_data.date_from is not None
                else None
            ),
            "date_to": (
                meta_data.date_to.isoformat()
                if meta_data.date_to is not None
                else None
            ),
        },
        "rows": [
            {
                "campaign_id": row.campaign_id,
                "campaign_name": row.campaign_name,
                "account_id": row.account_id,
                "account_name": row.account_name,
                "spend": float(row.spend),
                "ads_count": row.ads_count,
                "matched_ads_count": row.matched_ads_count,
                "meta_observed_leads": row.meta_observed_leads,
                "assignment_status": row.assignment_status,
                "sucursal_id": row.sucursal_id,
                "sucursal": (
                    branch_names.get(row.sucursal_id)
                    if row.sucursal_id is not None
                    else None
                ),
                "evidence_branch_ids": list(
                    row.evidence_branch_ids
                ),
                "date_from": (
                    meta_data.date_from.isoformat()
                    if meta_data.date_from is not None
                    else None
                ),
                "date_to": (
                    meta_data.date_to.isoformat()
                    if meta_data.date_to is not None
                    else None
                ),
                "impressions": row.impressions,
                "clicks": row.clicks,
            }
            for row in rows
        ],
    }
