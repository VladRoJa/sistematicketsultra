# backend/app/warehouse/scheduler/reports_scheduler_worker.py

from __future__ import annotations

import logging
import os
import signal
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from app import create_app
from app.extensions import db

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [reports-scheduler] %(message)s",
)

_SHOULD_STOP = False


def _handle_stop(signum, frame):  # noqa: ARG001
    global _SHOULD_STOP
    logger.info("Señal recibida: %s. Cerrando scheduler...", signum)
    _SHOULD_STOP = True


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)

    if raw is None or not raw.strip():
        return default

    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "Variable %s inválida=%r. Usando default=%s",
            name,
            raw,
            default,
        )
        return default


def _timezone() -> ZoneInfo:
    tz_name = os.getenv("REPORTS_SCHEDULER_TZ", "America/Tijuana").strip()

    if not tz_name:
        tz_name = "America/Tijuana"

    try:
        return ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001
        logger.warning(
            "Zona horaria inválida %r. Usando America/Tijuana.",
            tz_name,
        )
        return ZoneInfo("America/Tijuana")


def _now_local() -> datetime:
    return datetime.now(_timezone())


def run_scheduler_loop() -> None:
    enabled = _env_bool("REPORTS_SCHEDULER_ENABLED", True)
    sleep_seconds = max(_env_int("REPORTS_SCHEDULER_SLEEP_SECONDS", 60), 10)

    logger.info(
        "reports-scheduler iniciado. enabled=%s sleep=%ss",
        enabled,
        sleep_seconds,
    )

    if not enabled:
        logger.info("REPORTS_SCHEDULER_ENABLED=false. Scheduler inactivo.")
        return

    while not _SHOULD_STOP:
        try:
            now = _now_local()

            logger.info(
                "Ciclo activo. now=%s",
                now.isoformat(timespec="seconds"),
            )

            # Jobs futuros:
            # - cobranza_recurrente_rechazados_job

        except Exception:  # noqa: BLE001
            logger.exception("Error no controlado en ciclo de reports-scheduler.")
        finally:
            db.session.remove()

        time.sleep(sleep_seconds)

    logger.info("reports-scheduler detenido correctamente.")


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    app = create_app()

    with app.app_context():
        run_scheduler_loop()


if __name__ == "__main__":
    main()