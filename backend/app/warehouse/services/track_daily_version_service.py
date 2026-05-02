#   backend\app\warehouse\services\track_daily_version_service.py


from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from app.extensions import db
from app.models.warehouse import TrackDailyVersionORM


TRACK_DAILY_VERSION_TYPES = frozenset(
    {
        "preview_operativo",
        "base_nocturna_canonica",
        "cierre_canonico",
    }
)

TRACK_DAILY_VERSION_STATUSES = frozenset(
    {
        "pending",
        "running",
        "success",
        "failed",
        "replaced",
    }
)


class TrackDailyVersionServiceError(RuntimeError):
    """Error base del ciclo de versionado diario del Track."""


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_date(value: Any, *, field_name: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except Exception as exc:
            raise TrackDailyVersionServiceError(
                f"No se pudo convertir a date el campo {field_name!r}: {value!r}"
            ) from exc

    raise TrackDailyVersionServiceError(
        f"Valor inválido para {field_name!r}: {value!r}"
    )


def _ensure_datetime_utc(value: Any, *, field_name: str) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    if isinstance(value, str):
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"

        try:
            parsed = datetime.fromisoformat(normalized)
        except Exception as exc:
            raise TrackDailyVersionServiceError(
                f"No se pudo convertir a datetime el campo {field_name!r}: {value!r}"
            ) from exc

        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)

    raise TrackDailyVersionServiceError(
        f"Valor inválido para {field_name!r}: {value!r}"
    )


def _ensure_optional_datetime_utc(
    value: Any,
    *,
    field_name: str,
) -> datetime | None:
    if value is None:
        return None
    return _ensure_datetime_utc(value, field_name=field_name)


def _ensure_version_type(value: Any) -> str:
    normalized = str(value or "").strip()
    if normalized not in TRACK_DAILY_VERSION_TYPES:
        raise TrackDailyVersionServiceError(
            "version_type inválido. "
            f"Permitidos: {sorted(TRACK_DAILY_VERSION_TYPES)}"
        )
    return normalized


def _ensure_status(value: Any) -> str:
    normalized = str(value or "").strip()
    if normalized not in TRACK_DAILY_VERSION_STATUSES:
        raise TrackDailyVersionServiceError(
            "status inválido. "
            f"Permitidos: {sorted(TRACK_DAILY_VERSION_STATUSES)}"
        )
    return normalized


def _ensure_required_text(value: Any, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise TrackDailyVersionServiceError(
            f"El campo {field_name!r} es obligatorio."
        )
    return normalized


def _ensure_optional_text(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _ensure_retry_count(value: Any) -> int:
    if value is None:
        return 0

    try:
        normalized = int(value)
    except Exception as exc:
        raise TrackDailyVersionServiceError(
            f"retry_count inválido: {value!r}"
        ) from exc

    if normalized < 0:
        raise TrackDailyVersionServiceError(
            f"retry_count no puede ser negativo: {normalized!r}"
        )

    return normalized


def get_track_daily_version_by_id(version_id: int) -> TrackDailyVersionORM:
    version = db.session.get(TrackDailyVersionORM, version_id)
    if version is None:
        raise TrackDailyVersionServiceError(
            f"No existe TrackDailyVersionORM con id={version_id}."
        )
    return version


def get_current_track_daily_version(
    *,
    track_date: Any,
    version_type: Any,
) -> TrackDailyVersionORM | None:
    normalized_track_date = _ensure_date(track_date, field_name="track_date")
    normalized_version_type = _ensure_version_type(version_type)

    return (
        TrackDailyVersionORM.query.filter_by(
            track_date=normalized_track_date,
            version_type=normalized_version_type,
            is_current=True,
        )
        .order_by(TrackDailyVersionORM.id.desc())
        .first()
    )


def list_current_track_daily_versions_for_date(
    *,
    track_date: Any,
) -> list[TrackDailyVersionORM]:
    normalized_track_date = _ensure_date(track_date, field_name="track_date")

    return (
        TrackDailyVersionORM.query.filter_by(
            track_date=normalized_track_date,
            is_current=True,
        )
        .order_by(
            TrackDailyVersionORM.version_type.asc(),
            TrackDailyVersionORM.id.asc(),
        )
        .all()
    )


def create_track_daily_version(
    *,
    track_date: Any,
    version_type: Any,
    status: Any = "pending",
    generated_at_utc: Any = None,
    started_at_utc: Any = None,
    finished_at_utc: Any = None,
    is_current: bool = True,
    replaces_version_id: int | None = None,
    base_version_id: int | None = None,
    requested_by: Any = None,
    trigger_source: Any,
    retry_count: Any = 0,
    error_message: Any = None,
    auto_commit: bool = False,
) -> TrackDailyVersionORM:
    normalized_track_date = _ensure_date(track_date, field_name="track_date")
    normalized_version_type = _ensure_version_type(version_type)
    normalized_status = _ensure_status(status)
    normalized_trigger_source = _ensure_required_text(
        trigger_source,
        field_name="trigger_source",
    )

    if is_current:
        existing_current = get_current_track_daily_version(
            track_date=normalized_track_date,
            version_type=normalized_version_type,
        )
        if existing_current is not None:
            raise TrackDailyVersionServiceError(
                "Ya existe una versión current para "
                f"track_date={normalized_track_date.isoformat()} "
                f"y version_type={normalized_version_type!r}. "
                "Usa replace_current_track_daily_version(...) si quieres reemplazarla."
            )

    version = TrackDailyVersionORM(
        track_date=normalized_track_date,
        version_type=normalized_version_type,
        status=normalized_status,
        generated_at_utc=_ensure_optional_datetime_utc(
            generated_at_utc,
            field_name="generated_at_utc",
        ),
        started_at_utc=_ensure_optional_datetime_utc(
            started_at_utc,
            field_name="started_at_utc",
        ),
        finished_at_utc=_ensure_optional_datetime_utc(
            finished_at_utc,
            field_name="finished_at_utc",
        ),
        is_current=bool(is_current),
        replaces_version_id=replaces_version_id,
        base_version_id=base_version_id,
        requested_by=_ensure_optional_text(requested_by),
        trigger_source=normalized_trigger_source,
        retry_count=_ensure_retry_count(retry_count),
        error_message=_ensure_optional_text(error_message),
        created_at=_now_utc(),
        updated_at=_now_utc(),
    )

    db.session.add(version)
    db.session.flush()

    if auto_commit:
        db.session.commit()

    return version


def replace_current_track_daily_version(
    *,
    track_date: Any,
    version_type: Any,
    status: Any = "pending",
    generated_at_utc: Any = None,
    started_at_utc: Any = None,
    finished_at_utc: Any = None,
    base_version_id: int | None = None,
    requested_by: Any = None,
    trigger_source: Any,
    retry_count: Any = 0,
    error_message: Any = None,
    auto_commit: bool = False,
) -> TrackDailyVersionORM:
    normalized_track_date = _ensure_date(track_date, field_name="track_date")
    normalized_version_type = _ensure_version_type(version_type)
    normalized_now = _now_utc()

    current_version = get_current_track_daily_version(
        track_date=normalized_track_date,
        version_type=normalized_version_type,
    )

    replaces_version_id: int | None = None

    if current_version is not None:
        current_version.is_current = False
        current_version.status = "replaced"
        current_version.finished_at_utc = (
            _ensure_optional_datetime_utc(
                finished_at_utc,
                field_name="finished_at_utc",
            )
            or normalized_now
        )
        current_version.updated_at = normalized_now
        replaces_version_id = current_version.id

    new_version = create_track_daily_version(
        track_date=normalized_track_date,
        version_type=normalized_version_type,
        status=status,
        generated_at_utc=generated_at_utc,
        started_at_utc=started_at_utc,
        finished_at_utc=finished_at_utc,
        is_current=True,
        replaces_version_id=replaces_version_id,
        base_version_id=base_version_id,
        requested_by=requested_by,
        trigger_source=trigger_source,
        retry_count=retry_count,
        error_message=error_message,
        auto_commit=False,
    )

    if auto_commit:
        db.session.commit()

    return new_version


def mark_track_daily_version_running(
    *,
    version_id: int,
    started_at_utc: Any = None,
    auto_commit: bool = False,
) -> TrackDailyVersionORM:
    version = get_track_daily_version_by_id(version_id)
    version.status = "running"
    version.started_at_utc = (
        _ensure_optional_datetime_utc(
            started_at_utc,
            field_name="started_at_utc",
        )
        or _now_utc()
    )
    version.updated_at = _now_utc()

    db.session.flush()

    if auto_commit:
        db.session.commit()

    return version


def mark_track_daily_version_success(
    *,
    version_id: int,
    generated_at_utc: Any = None,
    finished_at_utc: Any = None,
    auto_commit: bool = False,
) -> TrackDailyVersionORM:
    version = get_track_daily_version_by_id(version_id)
    now_utc = _now_utc()

    version.status = "success"
    version.generated_at_utc = (
        _ensure_optional_datetime_utc(
            generated_at_utc,
            field_name="generated_at_utc",
        )
        or now_utc
    )
    version.finished_at_utc = (
        _ensure_optional_datetime_utc(
            finished_at_utc,
            field_name="finished_at_utc",
        )
        or now_utc
    )
    version.error_message = None
    version.updated_at = now_utc

    db.session.flush()

    if auto_commit:
        db.session.commit()

    return version


def mark_track_daily_version_failed(
    *,
    version_id: int,
    error_message: Any = None,
    finished_at_utc: Any = None,
    auto_commit: bool = False,
) -> TrackDailyVersionORM:
    version = get_track_daily_version_by_id(version_id)
    now_utc = _now_utc()

    version.status = "failed"
    version.error_message = _ensure_optional_text(error_message)
    version.finished_at_utc = (
        _ensure_optional_datetime_utc(
            finished_at_utc,
            field_name="finished_at_utc",
        )
        or now_utc
    )
    version.updated_at = now_utc

    db.session.flush()

    if auto_commit:
        db.session.commit()

    return version


def mark_track_daily_version_replaced(
    *,
    version_id: int,
    finished_at_utc: Any = None,
    auto_commit: bool = False,
) -> TrackDailyVersionORM:
    version = get_track_daily_version_by_id(version_id)
    now_utc = _now_utc()

    version.status = "replaced"
    version.is_current = False
    version.finished_at_utc = (
        _ensure_optional_datetime_utc(
            finished_at_utc,
            field_name="finished_at_utc",
        )
        or now_utc
    )
    version.updated_at = now_utc

    db.session.flush()

    if auto_commit:
        db.session.commit()

    return version