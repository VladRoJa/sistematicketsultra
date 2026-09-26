# backend/app/services/maintenance_preventive_scheduler_worker.py

from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime, time as dt_time, timedelta
from zoneinfo import ZoneInfo

from app import create_app, db
from app.services.maintenance_preventive_service import (
    materializar_programaciones_recurrentes,
)
from app.utils.pm_legacy_transition import tickets_preventive_v1_enabled


LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "America/Tijuana"
DEFAULT_RUN_TIME = "00:10"
DEFAULT_POLL_SECONDS = 60
DEFAULT_RETRY_MINUTES = 15


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {
        "1",
        "true",
        "yes",
        "si",
        "sí",
        "on",
        "enabled",
    }


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        LOGGER.warning(
            "Valor inválido para %s=%r. Usando default=%s.",
            name,
            raw,
            default,
        )
        return default


def _resolve_timezone() -> ZoneInfo:
    raw = (
        os.getenv("MAINTENANCE_PREVENTIVE_SCHEDULER_TZ")
        or DEFAULT_TIMEZONE
    ).strip()
    try:
        return ZoneInfo(raw)
    except Exception:
        LOGGER.warning(
            "Timezone inválido %r. Usando %s.",
            raw,
            DEFAULT_TIMEZONE,
        )
        return ZoneInfo(DEFAULT_TIMEZONE)


def _resolve_run_time() -> dt_time:
    raw = (
        os.getenv("MAINTENANCE_PREVENTIVE_RUN_TIME")
        or DEFAULT_RUN_TIME
    ).strip()
    try:
        parsed = datetime.strptime(raw, "%H:%M")
    except ValueError:
        LOGGER.warning(
            "Horario inválido %r. Usando %s.",
            raw,
            DEFAULT_RUN_TIME,
        )
        parsed = datetime.strptime(DEFAULT_RUN_TIME, "%H:%M")
    return parsed.time()


def _should_run(
    *,
    now_local: datetime,
    run_time: dt_time,
    last_success_date: date | None,
    next_retry_at: datetime | None,
) -> bool:
    if last_success_date == now_local.date():
        return False
    if now_local.time() < run_time:
        return False
    if next_retry_at is not None and now_local < next_retry_at:
        return False
    return True


def execute_recurring_preventive_materialization(
    *,
    business_date: date,
) -> dict:
    result = materializar_programaciones_recurrentes(
        through_date=business_date,
    )
    db.session.commit()
    return result


def run_scheduler_loop() -> None:
    enabled = _env_bool(
        "MAINTENANCE_PREVENTIVE_SCHEDULER_ENABLED",
        True,
    )
    poll_seconds = max(
        _env_int(
            "MAINTENANCE_PREVENTIVE_SCHEDULER_POLL_SECONDS",
            DEFAULT_POLL_SECONDS,
        ),
        10,
    )
    retry_minutes = max(
        _env_int(
            "MAINTENANCE_PREVENTIVE_RETRY_MINUTES",
            DEFAULT_RETRY_MINUTES,
        ),
        1,
    )
    scheduler_timezone = _resolve_timezone()
    run_time = _resolve_run_time()

    LOGGER.info(
        "Scheduler PM preventivo iniciado. enabled=%s timezone=%s "
        "run_time=%s poll_seconds=%s retry_minutes=%s",
        enabled,
        scheduler_timezone.key,
        run_time.strftime("%H:%M"),
        poll_seconds,
        retry_minutes,
    )

    app = create_app()
    last_success_date: date | None = None
    next_retry_at: datetime | None = None

    with app.app_context():
        while True:
            try:
                now_local = datetime.now(scheduler_timezone)

                if not enabled:
                    continue

                if not tickets_preventive_v1_enabled():
                    continue

                if not _should_run(
                    now_local=now_local,
                    run_time=run_time,
                    last_success_date=last_success_date,
                    next_retry_at=next_retry_at,
                ):
                    continue

                try:
                    result = execute_recurring_preventive_materialization(
                        business_date=now_local.date(),
                    )
                    last_success_date = now_local.date()
                    next_retry_at = None

                    LOGGER.info(
                        "PM recurrente materializado. date=%s considered=%s "
                        "generated=%s existing=%s errors=%s",
                        now_local.date().isoformat(),
                        result.get("considered"),
                        result.get("generated"),
                        result.get("already_existing"),
                        len(result.get("errors") or []),
                    )
                except Exception:
                    db.session.rollback()
                    next_retry_at = now_local + timedelta(
                        minutes=retry_minutes
                    )
                    LOGGER.exception(
                        "Falló materialización PM recurrente. "
                        "date=%s retry_at=%s",
                        now_local.date().isoformat(),
                        next_retry_at.isoformat(),
                    )
            finally:
                db.session.remove()
                time.sleep(poll_seconds)


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    run_scheduler_loop()
