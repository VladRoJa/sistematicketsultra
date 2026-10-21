"""Unit tests for the isolated historical Meta city spend allocator."""
from dataclasses import replace
from decimal import Decimal

import pytest

from app.services.marketing_meta_historical_allocation_service import (
    ESTIMATED_CITY_SPLIT,
    HistoricalMetaAdsetSource,
    allocate_historical_city_spend,
)


SOURCE = HistoricalMetaAdsetSource(
    period_key="META-2025-12",
    account_id="1394543581400837",
    campaign_id="120236276194360426",
    adset_id="120236276194480426",
    city_key="MEXICALI",
)


def _split(spend="36967.6900", branches=(1, 2, 3, 4, 5)):
    return allocate_historical_city_spend(
        source=SOURCE,
        spend=Decimal(spend),
        eligible_branch_ids=branches,
    )


def test_mexicali_december_2025_reconciles_exactly_to_meta_adset():
    allocations = _split()
    assert [(row.sucursal_id, row.spend) for row in allocations] == [
        (1, Decimal("7393.54")),
        (2, Decimal("7393.54")),
        (3, Decimal("7393.54")),
        (4, Decimal("7393.54")),
        (5, Decimal("7393.53")),
    ]
    assert sum((row.spend for row in allocations), Decimal("0")) == (
        Decimal("36967.6900")
    )
    assert all(row.source == SOURCE for row in allocations)
    assert all(row.allocation_method == ESTIMATED_CITY_SPLIT for row in allocations)


def test_remainder_is_deterministic_regardless_of_input_order():
    expected = _split("0.05", (1, 2, 3))
    actual = _split("0.05", (3, 1, 2))
    assert expected == actual
    assert [row.spend for row in actual] == [
        Decimal("0.02"),
        Decimal("0.02"),
        Decimal("0.01"),
    ]


def test_single_branch_gets_full_spend_and_zero_stays_zero():
    assert [(row.sucursal_id, row.spend) for row in _split("11.37", (4,))] == [
        (4, Decimal("11.37"))
    ]
    assert [row.spend for row in _split("0.00", (1, 2))] == [
        Decimal("0.00"),
        Decimal("0.00"),
    ]


def test_two_adsets_are_independent_and_reconcile_without_double_counting():
    first = _split("3.01", (1, 2))
    other_source = replace(SOURCE, adset_id="120236276194510426", city_key="TIJUANA")
    second = allocate_historical_city_spend(
        source=other_source,
        spend=Decimal("2.05"),
        eligible_branch_ids=(11, 12),
    )
    assert sum((row.spend for row in first + second), Decimal("0")) == Decimal(
        "5.06"
    )
    assert {row.source.adset_id for row in first + second} == {
        SOURCE.adset_id,
        other_source.adset_id,
    }


@pytest.mark.parametrize(
    "branches",
    [
        (),
        (1, 1),
        (1, 100),
        (1000,),
        (1, -2),
        (1, 0),
        (1, True),
        (1, "2"),
    ],
)
def test_rejects_missing_duplicate_administrative_or_invalid_branches(branches):
    with pytest.raises(ValueError):
        _split("1.00", branches)


@pytest.mark.parametrize(
    "spend",
    [
        Decimal("-0.01"),
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("1.001"),
    ],
)
def test_rejects_invalid_spend_without_rounding(spend):
    with pytest.raises(ValueError):
        allocate_historical_city_spend(
            source=SOURCE,
            spend=spend,
            eligible_branch_ids=(1, 2),
        )


def test_rejects_float_spend():
    with pytest.raises(TypeError):
        allocate_historical_city_spend(
            source=SOURCE,
            spend=36.97,
            eligible_branch_ids=(1, 2),
        )


@pytest.mark.parametrize(
    "source",
    [
        replace(SOURCE, period_key="META-2025-13"),
        replace(SOURCE, period_key="2025-12"),
        replace(SOURCE, adset_id=""),
        replace(SOURCE, city_key=" "),
    ],
)
def test_source_requires_valid_period_and_identity(source):
    with pytest.raises(ValueError):
        allocate_historical_city_spend(
            source=source,
            spend=Decimal("1.00"),
            eligible_branch_ids=(1,),
        )
