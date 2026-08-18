from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.extensions import db
from app.models.warehouse import TrackDailyMartORM, TrackDailyVersionORM
from app.warehouse.services.track_daily_version_service import (
    get_current_track_daily_version,
)


ALLOWED_TRACK_GENERATION_MODES = {
    "manual_preview",
    "official_closed_day",
}


def get_track_local_today() -> date:
    return datetime.now(ZoneInfo("America/Tijuana")).date()


def resolve_track_daily_version_type_candidates(
    *,
    track_date: date,
    generation_mode: str,
    today: date | None = None,
) -> list[str]:
    normalized_mode = str(generation_mode or "").strip()

    if normalized_mode not in ALLOWED_TRACK_GENERATION_MODES:
        raise ValueError(f"generation_mode inválido: {generation_mode!r}")

    if normalized_mode == "manual_preview" and track_date == (
        today or get_track_local_today()
    ):
        return ["preview_operativo"]

    return [
        "cierre_canonico",
        "base_nocturna_canonica",
    ]


def track_daily_version_has_mart_rows(*, version_id: int) -> bool:
    return (
        db.session.query(TrackDailyMartORM.id)
        .filter(TrackDailyMartORM.track_daily_version_id == version_id)
        .first()
        is not None
    )


def resolve_replaced_track_daily_version_with_rows(
    version: TrackDailyVersionORM | None,
) -> TrackDailyVersionORM | None:
    if version is None or not version.replaces_version_id:
        return None

    previous_version = db.session.get(
        TrackDailyVersionORM,
        version.replaces_version_id,
    )

    if previous_version is None:
        return None

    if previous_version.track_date != version.track_date:
        return None

    if previous_version.version_type != version.version_type:
        return None

    if previous_version.status not in {"success", "replaced"}:
        return None

    if not track_daily_version_has_mart_rows(
        version_id=previous_version.id,
    ):
        return None

    return previous_version


def resolve_effective_track_daily_version(
    *,
    track_date: date,
    generation_mode: str,
    today: date | None = None,
) -> TrackDailyVersionORM | None:
    for version_type in resolve_track_daily_version_type_candidates(
        track_date=track_date,
        generation_mode=generation_mode,
        today=today,
    ):
        version = get_current_track_daily_version(
            track_date=track_date,
            version_type=version_type,
        )

        if version is None:
            continue

        if (
            version.status == "success"
            and track_daily_version_has_mart_rows(version_id=version.id)
        ):
            return version

        fallback_version = resolve_replaced_track_daily_version_with_rows(
            version,
        )

        if fallback_version is not None:
            return fallback_version

    return None
