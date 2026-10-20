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

PREFERRED_TRACK_VERSION_TYPES = (
    "cierre_canonico",
    "base_nocturna_canonica",
    "preview_operativo",
)


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
    if version is None:
        return None

    current_version = version
    visited_version_ids: set[int] = {version.id}

    while current_version.replaces_version_id:
        previous_version_id = current_version.replaces_version_id

        if previous_version_id in visited_version_ids:
            return None

        visited_version_ids.add(previous_version_id)

        previous_version = db.session.get(
            TrackDailyVersionORM,
            previous_version_id,
        )

        if previous_version is None:
            return None

        if previous_version.track_date != version.track_date:
            return None

        if previous_version.version_type != version.version_type:
            return None

        if (
            previous_version.status in {"success", "replaced"}
            and track_daily_version_has_mart_rows(
                version_id=previous_version.id,
            )
        ):
            return previous_version

        current_version = previous_version

    return None


def resolve_preferred_track_daily_version(
    *,
    track_date: date,
) -> TrackDailyVersionORM | None:
    """Resuelve la mejor versión consultable de una fecha.

    Prioridad:
    1. cierre_canonico
    2. base_nocturna_canonica
    3. preview_operativo

    Cada candidata debe conservar las mismas garantías usadas por el
    resolver existente: versión current exitosa con filas de mart, o
    fallback válido hacia la versión reemplazada con filas.
    """

    for version_type in PREFERRED_TRACK_VERSION_TYPES:
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


def find_latest_effective_track_mart_row_for_branch(
    *,
    sucursal_canon: str,
    exact_target_month: date | None = None,
    latest_target_month: date | None = None,
    require_m2_sin_circulaciones: bool = False,
) -> TrackDailyMartORM | None:
    """Read a latest branch row ONLY through the public effective version.

    Candidate or replaced versions must never win merely by having a newer
    mart ID. The existing close > nightly > preview and replaced-row fallback
    contracts remain authoritative for every eligible business date.
    """
    candidate_dates = (
        db.session.query(TrackDailyMartORM.track_date)
        .join(
            TrackDailyVersionORM,
            TrackDailyVersionORM.id == TrackDailyMartORM.track_daily_version_id,
        )
        .filter(
            TrackDailyMartORM.sucursal_canon == sucursal_canon,
            TrackDailyVersionORM.version_type.in_(PREFERRED_TRACK_VERSION_TYPES),
            TrackDailyVersionORM.status.in_(("success", "replaced")),
        )
    )
    if exact_target_month is not None:
        candidate_dates = candidate_dates.filter(
            TrackDailyMartORM.target_month == exact_target_month,
        )
    if latest_target_month is not None:
        candidate_dates = candidate_dates.filter(
            TrackDailyMartORM.target_month <= latest_target_month,
        )
    if require_m2_sin_circulaciones:
        candidate_dates = candidate_dates.filter(
            TrackDailyMartORM.m2_sin_circulaciones.isnot(None),
        )

    for (track_date,) in (
        candidate_dates.distinct()
        .order_by(TrackDailyMartORM.track_date.desc())
        .all()
    ):
        effective_version = resolve_preferred_track_daily_version(
            track_date=track_date,
        )
        if effective_version is None:
            continue
        row_query = TrackDailyMartORM.query.filter_by(
            track_daily_version_id=effective_version.id,
            sucursal_canon=sucursal_canon,
        )
        if exact_target_month is not None:
            row_query = row_query.filter(
                TrackDailyMartORM.target_month == exact_target_month,
            )
        if latest_target_month is not None:
            row_query = row_query.filter(
                TrackDailyMartORM.target_month <= latest_target_month,
            )
        if require_m2_sin_circulaciones:
            row_query = row_query.filter(
                TrackDailyMartORM.m2_sin_circulaciones.isnot(None),
            )
        row = row_query.one_or_none()
        if row is not None:
            return row

    return None
