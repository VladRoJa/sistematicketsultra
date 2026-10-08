from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services import marketing_campaign_v2_schedule_service as service


NOW = datetime(2026, 10, 8, 16, 0, tzinfo=timezone.utc)


def test_none_schedule_is_immediate():
    result = service.normalize_campaign_v2_schedule(None, now=NOW)

    assert result.mode == "IMMEDIATE"
    assert result.timezone_name is None
    assert result.local_datetime is None
    assert result.scheduled_for_utc is None
    assert result.provider_send_at is None
    assert result.fingerprint_payload() is None
    assert result.serialize() is None


def test_tijuana_schedule_normalizes_to_provider_utc():
    result = service.normalize_campaign_v2_schedule(
        {
            "local_datetime": "2026-10-08T10:30:00",
            "timezone": "America/Tijuana",
        },
        now=NOW,
    )

    assert result.mode == "SCHEDULED"
    assert result.timezone_name == "America/Tijuana"
    assert result.local_datetime == "2026-10-08T10:30:00"
    assert result.scheduled_for_utc == datetime(
        2026,
        10,
        8,
        17,
        30,
        tzinfo=timezone.utc,
    )
    assert result.provider_send_at == "2026-10-08T17:30:00.000Z"
    assert result.fingerprint_payload() == {
        "timezone": "America/Tijuana",
        "local_datetime": "2026-10-08T10:30:00",
        "provider_send_at": "2026-10-08T17:30:00.000Z",
    }


def test_schedule_rejects_past_time():
    with pytest.raises(
        service.MarketingCampaignV2ScheduleValidationError,
        match="futuro",
    ):
        service.normalize_campaign_v2_schedule(
            {
                "local_datetime": "2026-10-08T08:00:00",
                "timezone": "America/Tijuana",
            },
            now=NOW,
        )


def test_schedule_rejects_embedded_offset():
    with pytest.raises(
        service.MarketingCampaignV2ScheduleValidationError,
        match="offset",
    ):
        service.normalize_campaign_v2_schedule(
            {
                "local_datetime": "2026-10-08T10:30:00-07:00",
                "timezone": "America/Tijuana",
            },
            now=NOW,
        )


def test_schedule_rejects_nonexistent_dst_local_time():
    with pytest.raises(
        service.MarketingCampaignV2ScheduleValidationError,
        match="no existe",
    ):
        service.normalize_campaign_v2_schedule(
            {
                "local_datetime": "2027-03-14T02:30:00",
                "timezone": "America/Tijuana",
            },
            now=NOW,
        )


def test_schedule_rejects_ambiguous_dst_local_time():
    with pytest.raises(
        service.MarketingCampaignV2ScheduleValidationError,
        match="ambiguo",
    ):
        service.normalize_campaign_v2_schedule(
            {
                "local_datetime": "2026-11-01T01:30:00",
                "timezone": "America/Tijuana",
            },
            now=NOW,
        )


def test_schedule_rejects_unknown_timezone():
    with pytest.raises(
        service.MarketingCampaignV2ScheduleValidationError,
        match="timezone IANA",
    ):
        service.normalize_campaign_v2_schedule(
            {
                "local_datetime": "2026-10-08T10:30:00",
                "timezone": "America/Not_A_Real_Zone",
            },
            now=NOW,
        )


def test_schedule_rejects_unknown_fields():
    with pytest.raises(
        service.MarketingCampaignV2ScheduleValidationError,
        match="campos no permitidos",
    ):
        service.normalize_campaign_v2_schedule(
            {
                "local_datetime": "2026-10-08T10:30:00",
                "timezone": "America/Tijuana",
                "sendAt": "browser-authoritative-not-allowed",
            },
            now=NOW,
        )
