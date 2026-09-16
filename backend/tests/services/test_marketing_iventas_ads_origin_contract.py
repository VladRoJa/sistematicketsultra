import pytest

from app.services.marketing_iventas_service import (
    normalize_iventas_contact,
)


def _raw_contact(**overrides):
    contact = {
        "id": "contact-ads-1",
        "name": "Lead Ads",
        "phone": "6861234567",
        "createdAt": "2026-09-15T15:00:00Z",
        "firstMessageAt": "2026-09-15T15:01:00Z",
        "lastOutboundMessageAt": None,
        "channel": None,
        "agent": None,
        "lastMessageStatus": None,
        "tags": [],
    }
    contact.update(overrides)
    return contact


def _normalize(contact):
    return normalize_iventas_contact(
        contact=contact,
        branch_code="villas-del-rey",
        sucursal_id=1,
    )


def test_provider_ads_origin_is_persistable_without_legacy_tag() -> None:
    normalized = _normalize(
        _raw_contact(
            isFromAds=True,
            adsSourceId="120999888777",
        )
    )

    assert normalized.is_from_ads is True
    assert normalized.ads_source_id == "120999888777"
    assert normalized.tags == ()


def test_provider_ads_flag_does_not_require_ads_source_id() -> None:
    normalized = _normalize(
        _raw_contact(
            isFromAds=True,
            adsSourceId=None,
        )
    )

    assert normalized.is_from_ads is True
    assert normalized.ads_source_id is None


def test_missing_provider_ads_fields_remains_historical_unknown() -> None:
    normalized = _normalize(_raw_contact())

    assert normalized.is_from_ads is None
    assert normalized.ads_source_id is None


def test_explicit_false_is_distinct_from_historical_unknown() -> None:
    without_provider_fields = _normalize(_raw_contact())
    explicit_not_ads = _normalize(
        _raw_contact(isFromAds=False)
    )

    assert explicit_not_ads.is_from_ads is False
    assert (
        explicit_not_ads.row_hash
        != without_provider_fields.row_hash
    )


def test_ads_source_id_participates_in_contact_row_hash() -> None:
    first = _normalize(
        _raw_contact(
            isFromAds=True,
            adsSourceId="ad-1",
        )
    )
    second = _normalize(
        _raw_contact(
            isFromAds=True,
            adsSourceId="ad-2",
        )
    )

    assert first.row_hash != second.row_hash


def test_is_from_ads_rejects_non_boolean_provider_value() -> None:
    with pytest.raises(
        ValueError,
        match="isFromAds debe ser boolean o null",
    ):
        _normalize(
            _raw_contact(isFromAds="true")
        )
