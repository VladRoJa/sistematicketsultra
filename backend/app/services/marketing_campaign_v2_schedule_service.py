"""Scheduling normalization for Campaign V2 dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


IMMEDIATE_MODE = "IMMEDIATE"
SCHEDULED_MODE = "SCHEDULED"


class MarketingCampaignV2ScheduleValidationError(ValueError):
    pass


@dataclass(frozen=True)
class CampaignV2DispatchSchedule:
    mode: str
    timezone_name: str | None
    local_datetime: str | None
    scheduled_for_utc: datetime | None
    provider_send_at: str | None

    def fingerprint_payload(self) -> dict[str, Any] | None:
        if self.mode == IMMEDIATE_MODE:
            return None
        return {
            "timezone": self.timezone_name,
            "local_datetime": self.local_datetime,
            "provider_send_at": self.provider_send_at,
        }

    def serialize(self) -> dict[str, Any] | None:
        if self.mode == IMMEDIATE_MODE:
            return None
        return {
            "timezone": self.timezone_name,
            "local_datetime": self.local_datetime,
            "scheduled_for_utc": (
                self.scheduled_for_utc.isoformat()
                if self.scheduled_for_utc is not None
                else None
            ),
            "provider_send_at": self.provider_send_at,
        }


def normalize_campaign_v2_schedule(
    value: Any,
    *,
    now: datetime | None = None,
) -> CampaignV2DispatchSchedule:
    if value is None:
        return CampaignV2DispatchSchedule(
            mode=IMMEDIATE_MODE,
            timezone_name=None,
            local_datetime=None,
            scheduled_for_utc=None,
            provider_send_at=None,
        )

    if not isinstance(value, dict):
        raise MarketingCampaignV2ScheduleValidationError(
            "schedule debe ser un objeto."
        )

    allowed = {"local_datetime", "timezone"}
    unknown = set(value) - allowed
    if unknown:
        raise MarketingCampaignV2ScheduleValidationError(
            "schedule contiene campos no permitidos."
        )

    timezone_name = _required_text(value.get("timezone"), "schedule.timezone")
    raw_local = _required_text(
        value.get("local_datetime"),
        "schedule.local_datetime",
    )

    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise MarketingCampaignV2ScheduleValidationError(
            "schedule.timezone no es un timezone IANA válido."
        ) from exc

    try:
        local_dt = datetime.fromisoformat(raw_local)
    except ValueError as exc:
        raise MarketingCampaignV2ScheduleValidationError(
            "schedule.local_datetime debe ser ISO 8601 local."
        ) from exc

    if local_dt.tzinfo is not None or local_dt.utcoffset() is not None:
        raise MarketingCampaignV2ScheduleValidationError(
            "schedule.local_datetime no debe incluir offset; timezone va separado."
        )
    if local_dt.microsecond:
        raise MarketingCampaignV2ScheduleValidationError(
            "schedule.local_datetime no admite fracciones de segundo."
        )

    utc_candidates = _valid_utc_candidates(local_dt, zone)
    if not utc_candidates:
        raise MarketingCampaignV2ScheduleValidationError(
            "schedule.local_datetime no existe en ese timezone por cambio horario."
        )
    if len(utc_candidates) > 1:
        raise MarketingCampaignV2ScheduleValidationError(
            "schedule.local_datetime es ambiguo en ese timezone por cambio horario."
        )

    scheduled_for_utc = utc_candidates[0]
    current = _normalize_now(now)
    if scheduled_for_utc <= current:
        raise MarketingCampaignV2ScheduleValidationError(
            "La fecha/hora programada debe estar en el futuro."
        )

    return CampaignV2DispatchSchedule(
        mode=SCHEDULED_MODE,
        timezone_name=timezone_name,
        local_datetime=local_dt.isoformat(timespec="seconds"),
        scheduled_for_utc=scheduled_for_utc,
        provider_send_at=_provider_iso_utc(scheduled_for_utc),
    )


def _valid_utc_candidates(
    local_dt: datetime,
    zone: ZoneInfo,
) -> list[datetime]:
    candidates: list[datetime] = []

    for fold in (0, 1):
        aware = local_dt.replace(tzinfo=zone, fold=fold)
        utc_value = aware.astimezone(timezone.utc)
        roundtrip = utc_value.astimezone(zone)

        if roundtrip.replace(tzinfo=None) != local_dt:
            continue
        if roundtrip.fold != fold:
            continue
        if utc_value not in candidates:
            candidates.append(utc_value)

    return candidates


def _provider_iso_utc(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _normalize_now(value: datetime | None) -> datetime:
    current = value if value is not None else datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise MarketingCampaignV2ScheduleValidationError(
            f"{field_name} debe ser texto."
        )
    normalized = value.strip()
    if not normalized:
        raise MarketingCampaignV2ScheduleValidationError(
            f"{field_name} es obligatorio."
        )
    return normalized
