"""Audit-locked Meta ad-set identity -> verified Warehouse -> cost split."""
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from app.services.marketing_meta_historical_allocation_service import (
    ESTIMATED_CITY_SPLIT,
)
from app.services.marketing_meta_historical_branch_evidence_service import (
    HistoricalCityBranchEvidence,
    NO_CANONICAL_SNAPSHOT,
    REQUIRES_REVIEW,
    VERIFIED,
)
from app.services.marketing_meta_historical_adset_city_service import (
    AUDITED_CITY,
    EVIDENCE_REQUIRED,
    READY_ESTIMATED_CITY_SPLIT,
    SOURCE_REVIEW_REQUIRED,
    UNMAPPED_SOURCE,
    MetaAdsetObservation,
    build_audited_meta_city_preview,
    identify_audited_meta_adset_city,
)


OBSERVED = MetaAdsetObservation(
    period_key="META-2025-12",
    sync_run_id=272,
    run_date_from=date(2025, 12, 1),
    run_date_to=date(2025, 12, 31),
    run_status="COMPLETED",
    run_accounts_failed=0,
    account_id="meta-account-from-runtime",
    campaign_id="120236276194360426",
    adset_id="120236276194480426",
    adset_name="2. Mexicali",
    spend=Decimal("36967.6900"),
    insight_rows=1,
)

EVIDENCE = HistoricalCityBranchEvidence(
    month_start=date(2025, 12, 1),
    city_key="MEXICALI",
    status=VERIFIED,
    eligible_branch_ids=(1, 2, 3, 4, 5),
    snapshot_ids=tuple(range(1, 12)),
    observed_branch_names=(
        "VILLAS DEL REY",
        "VILLA VERDE MEXICALI",
        "INDEPENDENCIA",
        "TEC MEXICALI",
        "SENDERO MEXICALI",
    ),
    unresolved_branch_names=(),
)


def test_exact_audited_meta_adset_identity():
    result = identify_audited_meta_adset_city(OBSERVED)
    assert result.status == AUDITED_CITY
    assert result.city_key == "MEXICALI"
    assert result.audit_reference == "META_DEC2025_RUN272_MEXICALI_ADSET_AUDIT"


def test_end_to_end_pure_preview_reconciles_december_2025():
    result = build_audited_meta_city_preview(
        observation=OBSERVED,
        warehouse_evidence=EVIDENCE,
    )
    assert result.status == READY_ESTIMATED_CITY_SPLIT
    assert result.warehouse_status == VERIFIED
    assert [(r.sucursal_id, r.spend) for r in result.allocations] == [
        (1, Decimal("7393.54")),
        (2, Decimal("7393.54")),
        (3, Decimal("7393.54")),
        (4, Decimal("7393.54")),
        (5, Decimal("7393.53")),
    ]
    assert sum((r.spend for r in result.allocations), Decimal("0")) == OBSERVED.spend
    assert all(r.allocation_method == ESTIMATED_CITY_SPLIT for r in result.allocations)
    assert all(r.source.account_id == OBSERVED.account_id for r in result.allocations)
    assert all(r.source.adset_id == OBSERVED.adset_id for r in result.allocations)


@pytest.mark.parametrize(
    "changed",
    [
        {"period_key": "META-2025-11"},
        {"period_key": "META-2026-12"},
        {"sync_run_id": 273},
        {"campaign_id": "generic-city-campaign"},
        {"adset_id": "another-adset"},
    ],
)
def test_unreviewed_identity_never_guesses_city_from_label(changed):
    result = identify_audited_meta_adset_city(replace(OBSERVED, **changed))
    assert result.status == UNMAPPED_SOURCE
    assert result.city_key is None


@pytest.mark.parametrize(
    "changed",
    [
        {"run_date_from": date(2025, 12, 2)},
        {"run_date_to": date(2025, 12, 30)},
        {"run_status": "PARTIAL"},
        {"run_accounts_failed": 1},
        {"account_id": ""},
        {"adset_name": "2. Tijuana"},
        {"adset_name": "Mexicali"},
        {"spend": Decimal("36967.70")},
        {"spend": Decimal("NaN")},
        {"spend": Decimal("-1")},
        {"insight_rows": 2},
    ],
)
def test_audited_identity_fails_closed_on_source_drift(changed):
    result = identify_audited_meta_adset_city(replace(OBSERVED, **changed))
    assert result.status == SOURCE_REVIEW_REQUIRED
    assert result.city_key is None


@pytest.mark.parametrize(
    "evidence",
    [
        None,
        replace(EVIDENCE, status=NO_CANONICAL_SNAPSHOT, eligible_branch_ids=()),
        replace(EVIDENCE, status=REQUIRES_REVIEW, eligible_branch_ids=()),
        replace(EVIDENCE, month_start=date(2025, 11, 1)),
        replace(EVIDENCE, city_key="TIJUANA"),
        replace(EVIDENCE, eligible_branch_ids=()),
    ],
)
def test_without_matching_warehouse_evidence_cannot_allocate(evidence):
    result = build_audited_meta_city_preview(
        observation=OBSERVED, warehouse_evidence=evidence,
    )
    assert result.status == EVIDENCE_REQUIRED
    assert result.allocations == ()


def test_unreviewed_adset_does_not_allocate_even_if_warehouse_verified():
    observation = replace(OBSERVED, adset_id="another-adset")
    result = build_audited_meta_city_preview(
        observation=observation, warehouse_evidence=EVIDENCE,
    )
    assert result.status == UNMAPPED_SOURCE
    assert result.allocations == ()


def test_changed_amount_does_not_allocate_despite_valid_evidence():
    result = build_audited_meta_city_preview(
        observation=replace(OBSERVED, spend=Decimal("100.00")),
        warehouse_evidence=EVIDENCE,
    )
    assert result.status == SOURCE_REVIEW_REQUIRED
    assert result.allocations == ()


def test_requires_observation_value_object():
    with pytest.raises(TypeError):
        identify_audited_meta_adset_city(None)
