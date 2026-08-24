from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime, time as dt_time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app import create_app, db
from app.services.ticket_attachment_cleanup_service import (
    cleanup_expired_ticket_attachments,
)
from app.warehouse.services.scheduler_priority_service import (
    has_active_track_work,
)


LOGGER = logging.getLogger(__name__)

DEFAULT_CLEANUP_TIMEZONE = "America/Tijuana"
DEFAULT_CLEANUP_RUN_TIME = "02:20"
DEFAULT_CLEANUP_POLL_INTERVAL_SECONDS = 60
DEFAULT_CLEANUP_BATCH_SIZE = 500


def _env_positive_int(
    name: str,
    default: int,
) -> int:
    raw_value = os.getenv(name)

    if raw_value is None or raw_value.strip() == "":
        return default

    try:
        value = int(raw_value)
    except ValueError:
        LOGGER.warning(
            "Valor inválido para %s=%r. Usando default=%s.",
            name,
            raw_value,
            default,
        )
        return default

    if value <= 0:
        LOGGER.warning(
            "Valor no positivo para %s=%r. Usando default=%s.",
            name,
            raw_value,
            default,
        )
        return default

    return value


def _resolve_timezone() -> ZoneInfo:
    timezone_name = (
        os.getenv("TICKET_ATTACHMENT_CLEANUP_TIMEZONE")
        or DEFAULT_CLEANUP_TIMEZONE
    ).strip()

    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        LOGGER.warning(
            "Timezone inválido %r. Usando %s.",
            timezone_name,
            DEFAULT_CLEANUP_TIMEZONE,
        )
        return ZoneInfo(DEFAULT_CLEANUP_TIMEZONE)


def _parse_run_time(value: str) -> dt_time:
    normalized = str(value or "").strip()

    try:
        hour_text, minute_text = normalized.split(
            ":",
            maxsplit=1,
        )

        return dt_time(
            hour=int(hour_text),
            minute=int(minute_text),
        )
    except (TypeError, ValueError):
        raise ValueError(
            "TICKET_ATTACHMENT_CLEANUP_RUN_TIME "
            "debe usar HH:MM."
        )


def _resolve_run_time() -> dt_time:
    raw_value = (
        os.getenv("TICKET_ATTACHMENT_CLEANUP_RUN_TIME")
        or DEFAULT_CLEANUP_RUN_TIME
    )

    try:
        return _parse_run_time(raw_value)
    except ValueError:
        LOGGER.warning(
            "Hora cleanup inválida %r. Usando %s.",
            raw_value,
            DEFAULT_CLEANUP_RUN_TIME,
        )
        return _parse_run_time(
            DEFAULT_CLEANUP_RUN_TIME
        )


def _should_run_cleanup(
    *,
    now_local: datetime,
    run_time: dt_time,
    last_run_date: date | None,
) -> bool:
    if last_run_date == now_local.date():
        return False

    current_time = dt_time(
        hour=now_local.hour,
        minute=now_local.minute,
        second=now_local.second,
    )

    return current_time >= run_time


def execute_ticket_attachment_cleanup() -> dict:
    batch_size = _env_positive_int(
        "TICKET_ATTACHMENT_CLEANUP_BATCH_SIZE",
        DEFAULT_CLEANUP_BATCH_SIZE,
    )

    LOGGER.info(
        "Ejecutando cleanup de adjuntos de tickets: "
        "batch_size=%s",
        batch_size,
    )

    result = cleanup_expired_ticket_attachments(
        limit=batch_size,
    )

    LOGGER.info(
        "Cleanup de adjuntos terminó: "
        "examined=%s marked_deleted=%s "
        "files_deleted=%s files_already_missing=%s "
        "failed=%s",
        result.get("examined"),
        result.get("marked_deleted"),
        result.get("files_deleted"),
        result.get("files_already_missing"),
        len(result.get("failed") or []),
    )

    if result.get("failed"):
        LOGGER.warning(
            "Cleanup de adjuntos tuvo fallos individuales: %s",
            result["failed"],
        )

    return result


def run_cleanup_loop() -> None:
    poll_interval_seconds = _env_positive_int(
        "TICKET_ATTACHMENT_CLEANUP_POLL_INTERVAL_SECONDS",
        DEFAULT_CLEANUP_POLL_INTERVAL_SECONDS,
    )

    scheduler_timezone = _resolve_timezone()
    run_time = _resolve_run_time()

    LOGGER.info(
        "Ticket attachment cleanup worker iniciado. "
        "timezone=%s run_time=%s poll_interval_seconds=%s",
        scheduler_timezone.key,
        run_time.strftime("%H:%M"),
        poll_interval_seconds,
    )

    app = create_app()
    last_run_date: date | None = None

    with app.app_context():
        while True:
            try:
                now_local = datetime.now(
                    scheduler_timezone
                )

                if _should_run_cleanup(
                    now_local=now_local,
                    run_time=run_time,
                    last_run_date=last_run_date,
                ):
                    if has_active_track_work():
                        LOGGER.debug(
                            "Cleanup de adjuntos diferido "
                            "porque Track está activo. now=%s",
                            now_local.isoformat(
                                timespec="seconds"
                            ),
                        )
                    else:
                        execute_ticket_attachment_cleanup()
                        last_run_date = now_local.date()

            except Exception:
                LOGGER.exception(
                    "Falló ciclo de cleanup de adjuntos "
                    "de tickets."
                )
            finally:
                db.session.remove()

            time.sleep(poll_interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_cleanup_loop()
