#   backend\app\warehouse\services\track_daily_version_service.py


from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
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




def get_latest_track_canonical_close_version(
    *,
    track_date: Any,
) -> TrackDailyVersionORM | None:
    """
    Devuelve el intento de cierre_canonico más reciente
    para una fecha, independientemente de su estado/current.
    """
    normalized_track_date = _ensure_date(
        track_date,
        field_name="track_date",
    )

    return (
        TrackDailyVersionORM.query.filter(
            TrackDailyVersionORM.track_date
            == normalized_track_date,
            TrackDailyVersionORM.version_type
            == "cierre_canonico",
        )
        .order_by(TrackDailyVersionORM.id.desc())
        .first()
    )

def request_track_canonical_close(
    *,
    track_date: Any,
    requested_by: Any = None,
    trigger_source: Any = "manual_canonical_close_request",
    auto_commit: bool = False,
) -> TrackDailyVersionORM:
    """
    Registra de forma persistente una solicitud de cierre canónico.

    La solicitud NO se vuelve current al crearse. Esto permite que una
    versión canónica exitosa anterior siga visible mientras el scheduler
    procesa el nuevo cierre.

    La fila base_nocturna_canonica se bloquea FOR UPDATE para serializar
    solicitudes concurrentes de la misma fecha.
    """
    normalized_track_date = _ensure_date(
        track_date,
        field_name="track_date",
    )
    normalized_trigger_source = _ensure_required_text(
        trigger_source,
        field_name="trigger_source",
    )
    normalized_requested_by = _ensure_optional_text(requested_by)

    base_version = (
        TrackDailyVersionORM.query.filter_by(
            track_date=normalized_track_date,
            version_type="base_nocturna_canonica",
            is_current=True,
        )
        .with_for_update()
        .one_or_none()
    )

    if base_version is None or base_version.status != "success":
        raise TrackDailyVersionServiceError(
            "No se puede solicitar cierre canónico sin una "
            "base_nocturna_canonica current y success para "
            f"track_date={normalized_track_date.isoformat()}."
        )

    current_close = get_current_track_daily_version(
        track_date=normalized_track_date,
        version_type="cierre_canonico",
    )

    if (
        current_close is not None
        and current_close.status in {"pending", "running"}
    ):
        return current_close

    existing_request = (
        TrackDailyVersionORM.query.filter(
            TrackDailyVersionORM.track_date == normalized_track_date,
            TrackDailyVersionORM.version_type == "cierre_canonico",
            TrackDailyVersionORM.is_current.is_(False),
            TrackDailyVersionORM.status.in_(("pending", "running")),
        )
        .order_by(TrackDailyVersionORM.id.desc())
        .first()
    )

    if existing_request is not None:
        return existing_request

    latest_failed_request = (
        TrackDailyVersionORM.query.filter(
            TrackDailyVersionORM.track_date == normalized_track_date,
            TrackDailyVersionORM.version_type == "cierre_canonico",
            TrackDailyVersionORM.status == "failed",
        )
        .order_by(TrackDailyVersionORM.id.desc())
        .first()
    )

    retry_count = (
        int(latest_failed_request.retry_count or 0) + 1
        if latest_failed_request is not None
        else 0
    )

    request_version = create_track_daily_version(
        track_date=normalized_track_date,
        version_type="cierre_canonico",
        status="pending",
        generated_at_utc=None,
        started_at_utc=None,
        finished_at_utc=None,
        is_current=False,
        replaces_version_id=(
            current_close.id
            if current_close is not None
            else None
        ),
        base_version_id=base_version.id,
        requested_by=normalized_requested_by,
        trigger_source=normalized_trigger_source,
        retry_count=retry_count,
        error_message=None,
        auto_commit=False,
    )

    if auto_commit:
        db.session.commit()

    return request_version




def claim_next_pending_track_canonical_close(
    *,
    lease_timeout_seconds: int = 7200,
    max_recovery_retries: int = 3,
    auto_commit: bool = False,
) -> TrackDailyVersionORM | None:
    """
    Reclama de forma exclusiva una solicitud de cierre_canonico.

    Prioridad:
    1. pending más antigua;
    2. running abandonada cuyo lease haya vencido.

    FOR UPDATE SKIP LOCKED evita que dos workers reclamen la misma fila.
    La solicitud permanece non-current durante todo el procesamiento.
    """
    try:
        normalized_lease_timeout = int(
            lease_timeout_seconds
        )
    except Exception as exc:
        raise TrackDailyVersionServiceError(
            "lease_timeout_seconds inválido: "
            f"{lease_timeout_seconds!r}"
        ) from exc

    if normalized_lease_timeout <= 0:
        raise TrackDailyVersionServiceError(
            "lease_timeout_seconds debe ser mayor que cero."
        )

    try:
        normalized_max_recovery_retries = int(
            max_recovery_retries
        )
    except Exception as exc:
        raise TrackDailyVersionServiceError(
            "max_recovery_retries inválido: "
            f"{max_recovery_retries!r}"
        ) from exc

    if normalized_max_recovery_retries < 0:
        raise TrackDailyVersionServiceError(
            "max_recovery_retries no puede ser negativo."
        )

    now_utc = _now_utc()
    stale_cutoff = now_utc - timedelta(
        seconds=normalized_lease_timeout
    )

    # Primero atendemos trabajo realmente pendiente.
    request_version = (
        TrackDailyVersionORM.query.filter(
            TrackDailyVersionORM.version_type
            == "cierre_canonico",
            TrackDailyVersionORM.status == "pending",
            TrackDailyVersionORM.is_current.is_(False),
        )
        .order_by(
            TrackDailyVersionORM.created_at.asc(),
            TrackDailyVersionORM.id.asc(),
        )
        .with_for_update(skip_locked=True)
        .first()
    )

    is_stale_recovery = False

    # Si no hay pending, buscamos un running cuyo lease expiró.
    if request_version is None:
        request_version = (
            TrackDailyVersionORM.query.filter(
                TrackDailyVersionORM.version_type
                == "cierre_canonico",
                TrackDailyVersionORM.status == "running",
                TrackDailyVersionORM.is_current.is_(False),
                TrackDailyVersionORM.updated_at
                <= stale_cutoff,
            )
            .order_by(
                TrackDailyVersionORM.updated_at.asc(),
                TrackDailyVersionORM.id.asc(),
            )
            .with_for_update(skip_locked=True)
            .first()
        )

        if request_version is None:
            return None

        is_stale_recovery = True

    current_retry_count = int(
        request_version.retry_count or 0
    )

    if (
        is_stale_recovery
        and current_retry_count
        >= normalized_max_recovery_retries
    ):
        request_version.status = "failed"
        request_version.finished_at_utc = now_utc
        request_version.updated_at = now_utc
        request_version.error_message = (
            "Cierre canónico abandonado: lease vencido y "
            "límite de recuperaciones automáticas agotado. "
            f"max_recovery_retries="
            f"{normalized_max_recovery_retries}."
        )

        db.session.flush()

        if auto_commit:
            db.session.commit()

        return None

    if is_stale_recovery:
        request_version.retry_count = (
            current_retry_count + 1
        )

    request_version.status = "running"
    request_version.started_at_utc = now_utc
    request_version.finished_at_utc = None
    request_version.error_message = None
    request_version.updated_at = now_utc

    db.session.flush()

    if auto_commit:
        db.session.commit()

    return request_version

def promote_track_canonical_close(
    *,
    version_id: int,
    generated_at_utc: Any = None,
    finished_at_utc: Any = None,
    auto_commit: bool = False,
) -> TrackDailyVersionORM:
    """
    Promueve una solicitud cierre_canonico ya procesada a current + success.

    La promoción ocurre solamente al final del trabajo. Si el cierre current
    cambió desde que se creó la solicitud, se rechaza la promoción para evitar
    que un trabajo obsoleto pise un cierre más reciente.
    """
    try:
        normalized_version_id = int(version_id)
    except Exception as exc:
        raise TrackDailyVersionServiceError(
            f"version_id inválido: {version_id!r}"
        ) from exc

    if normalized_version_id <= 0:
        raise TrackDailyVersionServiceError(
            "version_id debe ser un entero positivo."
        )

    request_version = (
        TrackDailyVersionORM.query.filter_by(
            id=normalized_version_id,
        )
        .with_for_update()
        .one_or_none()
    )

    if request_version is None:
        raise TrackDailyVersionServiceError(
            "No existe TrackDailyVersionORM con "
            f"id={normalized_version_id}."
        )

    if request_version.version_type != "cierre_canonico":
        raise TrackDailyVersionServiceError(
            "Solo se puede promover una versión cierre_canonico. "
            f"version_id={normalized_version_id} "
            f"version_type={request_version.version_type!r}."
        )

    if request_version.is_current:
        if request_version.status == "success":
            return request_version

        raise TrackDailyVersionServiceError(
            "La versión cierre_canonico ya es current pero no success. "
            f"version_id={normalized_version_id} "
            f"status={request_version.status!r}."
        )

    if request_version.status not in {"pending", "running"}:
        raise TrackDailyVersionServiceError(
            "Solo se puede promover un cierre_canonico "
            "en estado pending o running. "
            f"version_id={normalized_version_id} "
            f"status={request_version.status!r}."
        )

    current_close = (
        TrackDailyVersionORM.query.filter(
            TrackDailyVersionORM.track_date
            == request_version.track_date,
            TrackDailyVersionORM.version_type
            == "cierre_canonico",
            TrackDailyVersionORM.is_current.is_(True),
            TrackDailyVersionORM.id
            != request_version.id,
        )
        .with_for_update()
        .one_or_none()
    )

    expected_replaces_id = request_version.replaces_version_id
    actual_current_id = (
        current_close.id
        if current_close is not None
        else None
    )

    if actual_current_id != expected_replaces_id:
        raise TrackDailyVersionServiceError(
            "La solicitud de cierre canónico quedó obsoleta porque "
            "el cierre current cambió durante el procesamiento. "
            f"version_id={normalized_version_id} "
            f"expected_current_id={expected_replaces_id!r} "
            f"actual_current_id={actual_current_id!r}."
        )

    now_utc = _now_utc()

    if current_close is not None:
        current_close.is_current = False
        current_close.status = "replaced"
        current_close.finished_at_utc = now_utc
        current_close.updated_at = now_utc

        # Primero liberamos la restricción unique de current.
        db.session.flush()

    request_version.is_current = True
    request_version.status = "success"
    request_version.generated_at_utc = (
        _ensure_optional_datetime_utc(
            generated_at_utc,
            field_name="generated_at_utc",
        )
        or now_utc
    )
    request_version.finished_at_utc = (
        _ensure_optional_datetime_utc(
            finished_at_utc,
            field_name="finished_at_utc",
        )
        or now_utc
    )
    request_version.error_message = None
    request_version.updated_at = now_utc

    db.session.flush()

    if auto_commit:
        db.session.commit()

    return request_version

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