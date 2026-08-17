from __future__ import annotations

import logging
import os
import time

from app import create_app, db
from app.services.ticket_attachment_cleanup_service import (
    cleanup_expired_ticket_attachments,
)


LOGGER = logging.getLogger(__name__)

DEFAULT_CLEANUP_POLL_INTERVAL_SECONDS = 60 * 60
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


def execute_ticket_attachment_cleanup() -> dict:
    batch_size = _env_positive_int(
        "TICKET_ATTACHMENT_CLEANUP_BATCH_SIZE",
        DEFAULT_CLEANUP_BATCH_SIZE,
    )

    LOGGER.info(
        "Ejecutando cleanup de adjuntos de tickets: batch_size=%s",
        batch_size,
    )

    result = cleanup_expired_ticket_attachments(
        limit=batch_size,
    )

    LOGGER.info(
        "Cleanup de adjuntos terminó: "
        "examined=%s marked_deleted=%s "
        "files_deleted=%s files_already_missing=%s failed=%s",
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

    LOGGER.info(
        "Ticket attachment cleanup worker iniciado. "
        "poll_interval_seconds=%s",
        poll_interval_seconds,
    )

    app = create_app()

    with app.app_context():
        while True:
            try:
                execute_ticket_attachment_cleanup()
            except Exception:
                LOGGER.exception(
                    "Falló ciclo de cleanup de adjuntos de tickets."
                )
            finally:
                db.session.remove()

            time.sleep(poll_interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_cleanup_loop()
