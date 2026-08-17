import json
from decimal import Decimal

import pytest

from app.services.marketing_meta_service import (
    MarketingMetaParseError,
    MarketingMetaRawPageResponse,
    parse_meta_raw_page,
)


def _raw_response(row: dict) -> MarketingMetaRawPageResponse:
    return MarketingMetaRawPageResponse(
        http_status=200,
        request_cursor=None,
        raw_payload=json.dumps({"data": [row]}),
    )


def _base_row() -> dict:
    return {
        "account_id": "1319540356912183",
        "account_name": "ULTRAGYM 3",
        "campaign_id": "120251159837560114",
        "campaign_name": "Campaign",
        "adset_id": "120251159837580114",
        "adset_name": "Adset",
        "ad_id": "120251159837570114",
        "ad_name": "699 reel",
        "date_start": "2026-08-01",
        "date_stop": "2026-08-17",
        "spend": "0",
        "reach": "0",
        "actions": [],
    }


def test_meta_zero_delivery_allows_missing_impressions_and_clicks():
    page = parse_meta_raw_page(_raw_response(_base_row()))

    assert len(page.insights) == 1
    insight = page.insights[0]

    assert insight.spend == Decimal("0")
    assert insight.reach == 0
    assert insight.impressions == 0
    assert insight.clicks == 0


@pytest.mark.parametrize("field_name", ["reach", "impressions", "clicks"])
@pytest.mark.parametrize("missing_value", [None, ""])
def test_meta_delivery_null_or_empty_normalizes_to_zero(
    field_name,
    missing_value,
):
    row = _base_row()
    row["impressions"] = "0"
    row["clicks"] = "0"
    row[field_name] = missing_value

    page = parse_meta_raw_page(_raw_response(row))
    insight = page.insights[0]

    assert getattr(insight, field_name) == 0


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("reach", "abc"),
        ("impressions", "-1"),
        ("clicks", "1.5"),
    ],
)
def test_meta_delivery_present_invalid_value_still_fails(
    field_name,
    invalid_value,
):
    row = _base_row()
    row["impressions"] = "0"
    row["clicks"] = "0"
    row[field_name] = invalid_value

    with pytest.raises(MarketingMetaParseError):
        parse_meta_raw_page(_raw_response(row))
