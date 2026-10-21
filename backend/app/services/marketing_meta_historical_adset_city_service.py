"""Audited Meta ad-set -> city identity for historical spend previews.

No string guessing and no live Funnel reads. This manifest contains only
identities individually checked against completed Meta source runs. Each new
source requires separate evidence and an explicit manifest update.

Never infer leads, conversions, or a branch directly from ad-set labels.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.services.marketing_meta_historical_allocation_service import (
    HistoricalMetaAdsetSource,
    HistoricalMetaSpendAllocation,
    allocate_historical_city_spend,
)
from app.services.marketing_meta_historical_branch_evidence_service import (
    HistoricalCityBranchEvidence,
    VERIFIED,
)


AUDITED_CITY = "AUDITED_CITY"
UNMAPPED_SOURCE = "UNMAPPED_SOURCE"
SOURCE_REVIEW_REQUIRED = "SOURCE_REVIEW_REQUIRED"
EVIDENCE_REQUIRED = "EVIDENCE_REQUIRED"
READY_ESTIMATED_CITY_SPLIT = "READY_ESTIMATED_CITY_SPLIT"


@dataclass(frozen=True)
class MetaAdsetObservation:
    """One full ad-set amount from one completed, exact-period Meta run."""

    period_key: str
    sync_run_id: int
    run_date_from: date
    run_date_to: date
    run_status: str
    run_accounts_failed: int
    account_id: str
    campaign_id: str
    adset_id: str
    adset_name: str
    spend: Decimal
    insight_rows: int


@dataclass(frozen=True)
class AuditedCityIdentity:
    """Read-only review record: city and exact source ledger fingerprint."""

    period_key: str
    sync_run_id: int
    run_date_from: date
    run_date_to: date
    campaign_id: str
    adset_id: str
    adset_name: str
    spend: Decimal
    insight_rows: int
    city_key: str
    audit_reference: str


@dataclass(frozen=True)
class MetaHistoricalCityIdentification:
    status: str
    city_key: str | None
    audit_reference: str | None


@dataclass(frozen=True)
class MetaHistoricalCityPreview:
    status: str
    identification: MetaHistoricalCityIdentification
    warehouse_status: str | None
    allocations: tuple[HistoricalMetaSpendAllocation, ...]


# Evidence: completed production run 272, META-2025-12, one ad-set insight
# for "2. Mexicali", total spend 36967.6900. Warehouse December 2025:
# 11 canonical KPI snapshots, 24 branches, zero unresolved aliases, gym
# IDs 1-5 in municipio Mexicali. This registry is deliberately limited.
_REVIEWED_IDENTITIES = (
    AuditedCityIdentity(
        period_key="META-2025-12",
        sync_run_id=272,
        run_date_from=date(2025, 12, 1),
        run_date_to=date(2025, 12, 31),
        campaign_id="120236276194360426",
        adset_id="120236276194480426",
        adset_name="2. Mexicali",
        spend=Decimal("36967.6900"),
        insight_rows=1,
        city_key="MEXICALI",
        audit_reference="META_DEC2025_RUN272_MEXICALI_ADSET_AUDIT",
    ),
)


def identify_audited_meta_adset_city(
    observation: MetaAdsetObservation,
) -> MetaHistoricalCityIdentification:
    """Only accept exact audited run/ad-set and unchanged source amount.

    A reused label or a future re-run is NOT automatically authorized.
    """
    if not isinstance(observation, MetaAdsetObservation):
        raise TypeError("Se requiere una observación Meta identificada.")
    matches = [
        rule
        for rule in _REVIEWED_IDENTITIES
        if (
            rule.period_key == observation.period_key
            and rule.sync_run_id == observation.sync_run_id
            and rule.campaign_id == observation.campaign_id
            and rule.adset_id == observation.adset_id
        )
    ]
    if len(matches) != 1:
        return MetaHistoricalCityIdentification(UNMAPPED_SOURCE, None, None)

    rule = matches[0]
    valid = all((
        observation.run_date_from == rule.run_date_from,
        observation.run_date_to == rule.run_date_to,
        observation.run_status == "COMPLETED",
        type(observation.run_accounts_failed) is int,
        observation.run_accounts_failed == 0,
        isinstance(observation.account_id, str),
        bool(observation.account_id.strip()),
        observation.adset_name == rule.adset_name,
        isinstance(observation.spend, Decimal),
        observation.spend.is_finite() if isinstance(observation.spend, Decimal) else False,
        observation.spend == rule.spend,
        type(observation.insight_rows) is int,
        observation.insight_rows == rule.insight_rows,
    ))
    if not valid:
        return MetaHistoricalCityIdentification(SOURCE_REVIEW_REQUIRED, None, None)
    return MetaHistoricalCityIdentification(
        AUDITED_CITY, rule.city_key, rule.audit_reference,
    )


def build_audited_meta_city_preview(
    *,
    observation: MetaAdsetObservation,
    warehouse_evidence: HistoricalCityBranchEvidence | None,
) -> MetaHistoricalCityPreview:
    """Compose approved identity + verified monthly Warehouse + cent-safe split.

    Pure preview only: no DB access, writes, API, Funnel or canonical updates.
    A missing/partial/unknown source is never converted to zero cost.
    """
    identification = identify_audited_meta_adset_city(observation)
    if identification.status != AUDITED_CITY:
        return MetaHistoricalCityPreview(
            identification.status, identification, None, (),
        )
    if (
        warehouse_evidence is None
        or warehouse_evidence.status != VERIFIED
        or warehouse_evidence.city_key != identification.city_key
        or warehouse_evidence.month_start != observation.run_date_from
        or not warehouse_evidence.eligible_branch_ids
    ):
        return MetaHistoricalCityPreview(
            EVIDENCE_REQUIRED,
            identification,
            warehouse_evidence.status if warehouse_evidence else None,
            (),
        )

    source = HistoricalMetaAdsetSource(
        period_key=observation.period_key,
        account_id=observation.account_id,
        campaign_id=observation.campaign_id,
        adset_id=observation.adset_id,
        city_key=identification.city_key,
    )
    allocations = allocate_historical_city_spend(
        source=source,
        spend=observation.spend,
        eligible_branch_ids=warehouse_evidence.eligible_branch_ids,
    )
    return MetaHistoricalCityPreview(
        READY_ESTIMATED_CITY_SPLIT,
        identification,
        warehouse_evidence.status,
        allocations,
    )
