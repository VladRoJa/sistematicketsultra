from datetime import date, timedelta

import pytest

from app.services.marketing_iventas_service import (
    PHONE_STATUS_MISSING,
    PHONE_STATUS_MX10_MATCHABLE,
    PHONE_STATUS_NON_MX_OR_UNRESOLVED,
    build_iventas_utc_period,
    normalize_iventas_phone,
    normalize_iventas_contact,
    TAG_KIND_META_AD,
    TAG_KIND_OTHER,
    parse_iventas_timestamp,
)


def test_summer_period_uses_tijuana_dst() -> None:
    period = build_iventas_utc_period(
        date_from=date(2026, 8, 1),
        date_to=date(2026, 8, 2),
    )

    assert (
        period.from_iso_z
        == "2026-08-01T07:00:00.000Z"
    )

    assert (
        period.to_iso_z
        == "2026-08-03T06:59:59.999Z"
    )


def test_winter_period_uses_tijuana_standard_time() -> None:
    period = build_iventas_utc_period(
        date_from=date(2026, 1, 10),
        date_to=date(2026, 1, 10),
    )

    assert (
        period.from_iso_z
        == "2026-01-10T08:00:00.000Z"
    )

    assert (
        period.to_iso_z
        == "2026-01-11T07:59:59.999Z"
    )


def test_period_crossing_dst_transition_keeps_real_offsets() -> None:
    period = build_iventas_utc_period(
        date_from=date(2026, 3, 7),
        date_to=date(2026, 3, 9),
    )

    assert (
        period.from_iso_z
        == "2026-03-07T08:00:00.000Z"
    )

    assert (
        period.to_iso_z
        == "2026-03-10T06:59:59.999Z"
    )


def test_single_day_is_valid() -> None:
    period = build_iventas_utc_period(
        date_from=date(2026, 8, 8),
        date_to=date(2026, 8, 8),
    )

    assert period.date_from == date(
        2026,
        8,
        8,
    )

    assert period.date_to == date(
        2026,
        8,
        8,
    )


def test_31_civil_days_are_valid() -> None:
    date_from = date(
        2026,
        7,
        1,
    )

    date_to = (
        date_from
        + timedelta(days=30)
    )

    period = build_iventas_utc_period(
        date_from=date_from,
        date_to=date_to,
    )

    assert period.date_from == date_from
    assert period.date_to == date_to


def test_32_civil_days_are_rejected() -> None:
    date_from = date(
        2026,
        7,
        1,
    )

    date_to = (
        date_from
        + timedelta(days=31)
    )

    with pytest.raises(
        ValueError,
        match="31 días civiles",
    ):
        build_iventas_utc_period(
            date_from=date_from,
            date_to=date_to,
        )


def test_inverted_period_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="anterior",
    ):
        build_iventas_utc_period(
            date_from=date(
                2026,
                8,
                9,
            ),
            date_to=date(
                2026,
                8,
                8,
            ),
        )


def test_iso_output_uses_exact_milliseconds() -> None:
    period = build_iventas_utc_period(
        date_from=date(2026, 8, 1),
        date_to=date(2026, 8, 1),
    )

    assert period.from_iso_z.endswith(
        ".000Z"
    )

    assert period.to_iso_z.endswith(
        ".999Z"
    )

    assert "." in period.from_iso_z
    assert "." in period.to_iso_z

    assert (
        len(
            period.from_iso_z.split(".")[1]
        )
        == 4
    )

    assert (
        len(
            period.to_iso_z.split(".")[1]
        )
        == 4
    )


def test_phone_plain_mx10_is_matchable() -> None:
    result = normalize_iventas_phone(
        "6861234567"
    )

    assert result.phone_raw == "6861234567"
    assert result.phone_digits == "6861234567"
    assert result.phone_mx10 == "6861234567"
    assert (
        result.phone_match_status
        == PHONE_STATUS_MX10_MATCHABLE
    )


def test_phone_52_plus_10_is_matchable() -> None:
    result = normalize_iventas_phone(
        "+52 686 123 4567"
    )

    assert (
        result.phone_raw
        == "+52 686 123 4567"
    )

    assert (
        result.phone_digits
        == "526861234567"
    )

    assert result.phone_mx10 == "6861234567"

    assert (
        result.phone_match_status
        == PHONE_STATUS_MX10_MATCHABLE
    )


def test_phone_521_plus_10_is_matchable() -> None:
    result = normalize_iventas_phone(
        "+52 1 686 123 4567"
    )

    assert (
        result.phone_digits
        == "5216861234567"
    )

    assert result.phone_mx10 == "6861234567"

    assert (
        result.phone_match_status
        == PHONE_STATUS_MX10_MATCHABLE
    )


def test_phone_formatting_is_removed_only_from_digits() -> None:
    raw = "(686) 123-45-67"

    result = normalize_iventas_phone(raw)

    assert result.phone_raw == raw
    assert result.phone_digits == "6861234567"
    assert result.phone_mx10 == "6861234567"


def test_international_phone_is_preserved_not_forced_to_mx10(
) -> None:
    result = normalize_iventas_phone(
        "+1 619 555 0123"
    )

    assert (
        result.phone_raw
        == "+1 619 555 0123"
    )

    assert (
        result.phone_digits
        == "16195550123"
    )

    assert result.phone_mx10 is None

    assert (
        result.phone_match_status
        == PHONE_STATUS_NON_MX_OR_UNRESOLVED
    )


def test_unresolved_numeric_format_is_preserved() -> None:
    result = normalize_iventas_phone(
        "0446861234567"
    )

    assert (
        result.phone_digits
        == "0446861234567"
    )

    assert result.phone_mx10 is None

    assert (
        result.phone_match_status
        == PHONE_STATUS_NON_MX_OR_UNRESOLVED
    )


def test_none_phone_is_missing() -> None:
    result = normalize_iventas_phone(None)

    assert result.phone_raw is None
    assert result.phone_digits is None
    assert result.phone_mx10 is None

    assert (
        result.phone_match_status
        == PHONE_STATUS_MISSING
    )


def test_blank_phone_is_missing_but_raw_is_preserved() -> None:
    result = normalize_iventas_phone(
        "   "
    )

    assert result.phone_raw == "   "
    assert result.phone_digits is None
    assert result.phone_mx10 is None

    assert (
        result.phone_match_status
        == PHONE_STATUS_MISSING
    )


def test_present_non_numeric_phone_is_unresolved() -> None:
    result = normalize_iventas_phone(
        "sin telefono"
    )

    assert (
        result.phone_raw
        == "sin telefono"
    )

    assert result.phone_digits is None
    assert result.phone_mx10 is None

    assert (
        result.phone_match_status
        == PHONE_STATUS_NON_MX_OR_UNRESOLVED
    )


def test_numeric_phone_value_is_preserved_as_text() -> None:
    result = normalize_iventas_phone(
        6861234567
    )

    assert result.phone_raw == "6861234567"
    assert result.phone_digits == "6861234567"
    assert result.phone_mx10 == "6861234567"

    assert (
        result.phone_match_status
        == PHONE_STATUS_MX10_MATCHABLE
    )


def test_timestamp_z_is_normalized_to_utc() -> None:
    result = parse_iventas_timestamp(
        "2026-08-01T18:30:45.123Z"
    )

    assert result is not None

    assert (
        result.utc_aware.isoformat()
        == "2026-08-01T18:30:45.123000+00:00"
    )


def test_timestamp_offset_is_converted_to_utc() -> None:
    result = parse_iventas_timestamp(
        "2026-08-01T11:30:45.123-07:00"
    )

    assert result is not None

    assert (
        result.utc_aware.isoformat()
        == "2026-08-01T18:30:45.123000+00:00"
    )


def test_timestamp_builds_tijuana_civil_datetime() -> None:
    result = parse_iventas_timestamp(
        "2026-08-01T18:30:45Z"
    )

    assert result is not None

    assert (
        result.local_tijuana_naive.isoformat()
        == "2026-08-01T11:30:45"
    )

    assert (
        result.local_tijuana_naive.tzinfo
        is None
    )


def test_timestamp_can_cross_local_calendar_date() -> None:
    result = parse_iventas_timestamp(
        "2026-08-01T06:30:00Z"
    )

    assert result is not None

    assert (
        result.local_tijuana_naive.isoformat()
        == "2026-07-31T23:30:00"
    )

    assert (
        result.local_tijuana_date
        == date(2026, 7, 31)
    )


def test_timestamp_uses_winter_tijuana_offset() -> None:
    result = parse_iventas_timestamp(
        "2026-01-10T18:00:00Z"
    )

    assert result is not None

    assert (
        result.local_tijuana_naive.isoformat()
        == "2026-01-10T10:00:00"
    )

    assert (
        result.local_tijuana_date
        == date(2026, 1, 10)
    )


def test_timestamp_none_and_blank_are_missing() -> None:
    assert (
        parse_iventas_timestamp(None)
        is None
    )

    assert (
        parse_iventas_timestamp("")
        is None
    )

    assert (
        parse_iventas_timestamp("   ")
        is None
    )


def test_timestamp_invalid_value_returns_none() -> None:
    assert (
        parse_iventas_timestamp(
            "not-a-timestamp"
        )
        is None
    )


def test_timestamp_without_timezone_is_rejected() -> None:
    result = parse_iventas_timestamp(
        "2026-08-01T11:30:45"
    )

    assert result is None


def _sample_iventas_contact() -> dict:
    return {
        "id": "contact-001",
        "name": "Contacto Prueba",
        "phone": "+52 686 123 4567",
        "createdAt": (
            "2026-08-01T18:30:45.123Z"
        ),
        "firstMessageAt": (
            "2026-08-01T18:35:00.000Z"
        ),
        "lastOutboundMessageAt": (
            "2026-08-01T19:00:00.000Z"
        ),
        "lastMessageStatus": "delivered",
        "channel": {
            "id": "channel-01",
            "name": "Canal prueba",
            "phone": "526861111111",
            "platform": "whatsapp",
        },
        "agent": {
            "id": "agent-01",
            "name": "Agente prueba",
        },
        "tags": [
            "ad_fb_123456789",
            "seguimiento",
        ],
    }


def test_contact_normalizes_complete_structure() -> None:
    result = normalize_iventas_contact(
        contact=_sample_iventas_contact(),
        branch_code="papalote",
        sucursal_id=13,
    )

    assert result.sucursal_id == 13
    assert result.branch_code == "papalote"
    assert result.contact_id == "contact-001"

    assert (
        result.phone_mx10
        == "6861234567"
    )

    assert (
        result.created_at_utc.isoformat()
        == "2026-08-01T18:30:45.123000+00:00"
    )

    assert (
        result.created_at_local.isoformat()
        == "2026-08-01T11:30:45.123000"
    )

    assert (
        result.created_date_local
        == date(2026, 8, 1)
    )

    assert result.channel_id == "channel-01"
    assert result.channel_name == "Canal prueba"
    assert result.channel_phone == "526861111111"
    assert result.channel_platform == "whatsapp"

    assert result.agent_json == {
        "id": "agent-01",
        "name": "Agente prueba",
    }

    assert (
        result.last_message_status
        == "delivered"
    )

    assert (
        result.last_outbound_message_at_utc
        is not None
    )

    assert len(result.row_hash) == 64


def test_contact_tags_are_classified() -> None:
    result = normalize_iventas_contact(
        contact=_sample_iventas_contact(),
        branch_code="papalote",
        sucursal_id=13,
    )

    assert len(result.tags) == 2

    meta = result.tags[0]
    other = result.tags[1]

    assert meta.tag_raw == "ad_fb_123456789"
    assert meta.tag_kind == TAG_KIND_META_AD
    assert meta.meta_ad_id == "123456789"

    assert other.tag_raw == "seguimiento"
    assert other.tag_kind == TAG_KIND_OTHER
    assert other.meta_ad_id is None


def test_contact_duplicate_tag_is_deduplicated() -> None:
    contact = _sample_iventas_contact()

    contact["tags"] = [
        "ad_fb_123456789",
        "ad_fb_123456789",
        "seguimiento",
        "seguimiento",
    ]

    result = normalize_iventas_contact(
        contact=contact,
        branch_code="papalote",
        sucursal_id=13,
    )

    assert [
        tag.tag_raw
        for tag in result.tags
    ] == [
        "ad_fb_123456789",
        "seguimiento",
    ]


def test_contact_requires_id() -> None:
    contact = _sample_iventas_contact()
    contact["id"] = None

    with pytest.raises(
        ValueError,
        match="id válido",
    ):
        normalize_iventas_contact(
            contact=contact,
            branch_code="papalote",
            sucursal_id=13,
        )


def test_contact_requires_valid_created_at() -> None:
    contact = _sample_iventas_contact()
    contact["createdAt"] = "invalid"

    with pytest.raises(
        ValueError,
        match="createdAt",
    ):
        normalize_iventas_contact(
            contact=contact,
            branch_code="papalote",
            sucursal_id=13,
        )


def test_contact_allows_missing_first_message() -> None:
    contact = _sample_iventas_contact()
    contact["firstMessageAt"] = None

    result = normalize_iventas_contact(
        contact=contact,
        branch_code="papalote",
        sucursal_id=13,
    )

    assert result.first_message_at_utc is None
    assert result.first_message_at_local is None
    assert result.first_message_date_local is None


def test_contact_allows_missing_last_outbound() -> None:
    contact = _sample_iventas_contact()
    contact["lastOutboundMessageAt"] = None

    result = normalize_iventas_contact(
        contact=contact,
        branch_code="papalote",
        sucursal_id=13,
    )

    assert (
        result.last_outbound_message_at_utc
        is None
    )


def test_contact_rejects_invalid_channel_shape() -> None:
    contact = _sample_iventas_contact()
    contact["channel"] = "not-an-object"

    with pytest.raises(
        ValueError,
        match="channel",
    ):
        normalize_iventas_contact(
            contact=contact,
            branch_code="papalote",
            sucursal_id=13,
        )


def test_contact_rejects_invalid_agent_shape() -> None:
    contact = _sample_iventas_contact()
    contact["agent"] = ["bad"]

    with pytest.raises(
        ValueError,
        match="agent",
    ):
        normalize_iventas_contact(
            contact=contact,
            branch_code="papalote",
            sucursal_id=13,
        )


def test_contact_rejects_invalid_tags_shape() -> None:
    contact = _sample_iventas_contact()
    contact["tags"] = {
        "not": "a-list",
    }

    with pytest.raises(
        ValueError,
        match="tags",
    ):
        normalize_iventas_contact(
            contact=contact,
            branch_code="papalote",
            sucursal_id=13,
        )


def test_contact_row_hash_is_deterministic() -> None:
    first = _sample_iventas_contact()

    second = {
        key: first[key]
        for key in reversed(
            list(first.keys())
        )
    }

    # También cambia el orden interno de agent;
    # JSON canónico debe neutralizarlo.
    second["agent"] = {
        "name": "Agente prueba",
        "id": "agent-01",
    }

    result_a = normalize_iventas_contact(
        contact=first,
        branch_code="papalote",
        sucursal_id=13,
    )

    result_b = normalize_iventas_contact(
        contact=second,
        branch_code="papalote",
        sucursal_id=13,
    )

    assert result_a.row_hash == result_b.row_hash
    assert len(result_a.row_hash) == 64

    int(
        result_a.row_hash,
        16,
    )


def test_contact_row_hash_changes_when_contact_row_changes(
) -> None:
    first = _sample_iventas_contact()
    second = _sample_iventas_contact()

    second["lastMessageStatus"] = "read"

    result_a = normalize_iventas_contact(
        contact=first,
        branch_code="papalote",
        sucursal_id=13,
    )

    result_b = normalize_iventas_contact(
        contact=second,
        branch_code="papalote",
        sucursal_id=13,
    )

    assert result_a.row_hash != result_b.row_hash


def test_contact_row_hash_excludes_tags() -> None:
    first = _sample_iventas_contact()
    second = _sample_iventas_contact()

    second["tags"] = [
        "otro_tag",
        "ad_fb_999999999",
    ]

    result_a = normalize_iventas_contact(
        contact=first,
        branch_code="papalote",
        sucursal_id=13,
    )

    result_b = normalize_iventas_contact(
        contact=second,
        branch_code="papalote",
        sucursal_id=13,
    )

    assert result_a.row_hash == result_b.row_hash

    assert (
        result_a.tags
        != result_b.tags
    )


def test_contact_row_hash_includes_branch_and_sucursal(
) -> None:
    contact = _sample_iventas_contact()

    base = normalize_iventas_contact(
        contact=contact,
        branch_code="papalote",
        sucursal_id=13,
    )

    other_branch = normalize_iventas_contact(
        contact=contact,
        branch_code="carrousel",
        sucursal_id=12,
    )

    assert (
        base.row_hash
        != other_branch.row_hash
    )
