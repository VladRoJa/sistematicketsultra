from __future__ import annotations

from datetime import datetime

from app.extensions import db
from app.models.warehouse import TrackDailyVersionORM


TRACK_ACTIVE_STATUSES = (
    "pending",
    "running",
)

SECONDARY_WINDOW_START_HOUR = 5
SECONDARY_WINDOW_END_HOUR = 22
SECONDARY_WINDOW_START_MINUTE = 20
SECONDARY_WINDOW_END_MINUTE = 44


def is_secondary_execution_window(
    now_local: datetime,
) -> bool:
    """
    Devuelve True únicamente dentro de una ventana segura
    para jobs secundarios.

    Track conserva prioridad alrededor de cada HH:00:
    - HH:00-HH:19: reservado después del arranque Track.
    - HH:45-HH:59: reservado antes del siguiente Track.

    También se evita iniciar jobs secundarios durante
    la ventana nocturna donde Track ejecuta sus procesos
    especiales.
    """

    if (
        now_local.hour < SECONDARY_WINDOW_START_HOUR
        or now_local.hour > SECONDARY_WINDOW_END_HOUR
    ):
        return False

    return (
        SECONDARY_WINDOW_START_MINUTE
        <= now_local.minute
        <= SECONDARY_WINDOW_END_MINUTE
    )


def has_active_track_work() -> bool:
    """
    Detecta trabajo Track actual que todavía debe tener
    prioridad sobre schedulers secundarios.
    """

    active_version = (
        db.session.query(
            TrackDailyVersionORM.id
        )
        .filter(
            TrackDailyVersionORM.is_current.is_(True),
            TrackDailyVersionORM.status.in_(
                TRACK_ACTIVE_STATUSES
            ),
        )
        .first()
    )

    return active_version is not None


def get_secondary_job_block_reason(
    now_local: datetime,
) -> str | None:
    if not is_secondary_execution_window(
        now_local
    ):
        return "track_reserved_window"

    if has_active_track_work():
        return "track_active"

    return None
