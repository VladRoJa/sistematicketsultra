# backend/app/warehouse/scheduler/reports_scheduler_worker.py

from __future__ import annotations

import logging
import os
import signal
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app import create_app
from app.extensions import db
from app.warehouse.jobs.cobranza_recurrente_rechazados_job import (
    CobranzaRecurrenteNotReadyError,
    run_job as run_cobranza_recurrente_job,
)

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [reports-scheduler] %(message)s",
)

_SHOULD_STOP = False

_COMPLETED_BY_JOB_AND_DATE: set[tuple[str, date]] = set()
_NEXT_RETRY_BY_JOB_AND_DATE: dict[tuple[str, date], datetime] = {}


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


def _clamp(value: int, *, minimum: int, maximum: int) -> int:
    return max(min(value, maximum), minimum)


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


def _scheduled_datetime(
    *,
    now: datetime,
    hour_env: str,
    minute_env: str,
    default_hour: int,
    default_minute: int,
) -> datetime:
    run_hour = _clamp(_env_int(hour_env, default_hour), minimum=0, maximum=23)
    run_minute = _clamp(_env_int(minute_env, default_minute), minimum=0, maximum=59)

    return now.replace(
        hour=run_hour,
        minute=run_minute,
        second=0,
        microsecond=0,
    )


def _job_date_key(job_key: str, business_date: date) -> tuple[str, date]:
    return job_key, business_date


def _mark_job_as_completed(job_key: str, business_date: date) -> None:
    run_key = _job_date_key(job_key, business_date)
    _COMPLETED_BY_JOB_AND_DATE.add(run_key)
    _NEXT_RETRY_BY_JOB_AND_DATE.pop(run_key, None)


def _schedule_retry(
    *,
    job_key: str,
    business_date: date,
    now: datetime,
    retry_minutes: int,
    reason: str,
) -> datetime:
    run_key = _job_date_key(job_key, business_date)
    next_retry_at = now + timedelta(minutes=retry_minutes)
    _NEXT_RETRY_BY_JOB_AND_DATE[run_key] = next_retry_at

    logger.warning(
        "%s no quedó completado. reason=%s business_date=%s next_retry_at=%s",
        job_key,
        reason,
        business_date.isoformat(),
        next_retry_at.isoformat(timespec="seconds"),
    )

    return next_retry_at


def _should_run_daily_job(
    *,
    job_key: str,
    enabled_env: str,
    hour_env: str,
    minute_env: str,
    now: datetime,
    default_hour: int,
    default_minute: int,
) -> bool:
    enabled = _env_bool(enabled_env, False)

    if not enabled:
        return False

    business_date = now.date()
    run_key = _job_date_key(job_key, business_date)

    if run_key in _COMPLETED_BY_JOB_AND_DATE:
        return False

    scheduled_at = _scheduled_datetime(
        now=now,
        hour_env=hour_env,
        minute_env=minute_env,
        default_hour=default_hour,
        default_minute=default_minute,
    )

    if now < scheduled_at:
        return False

    next_retry_at = _NEXT_RETRY_BY_JOB_AND_DATE.get(run_key)

    if next_retry_at and now < next_retry_at:
        return False

    return True


def _run_cobranza_recurrente_if_due(now: datetime) -> None:
    job_key = "cobranza_recurrente_rechazados"

    if not _should_run_daily_job(
        job_key=job_key,
        enabled_env="COBRANZA_RECURRENTE_ENABLED",
        hour_env="COBRANZA_RECURRENTE_RUN_HOUR",
        minute_env="COBRANZA_RECURRENTE_RUN_MINUTE",
        now=now,
        default_hour=8,
        default_minute=0,
    ):
        return

    business_date = now.date()
    retry_minutes = max(_env_int("COBRANZA_RECURRENTE_RETRY_MINUTES", 30), 5)

    logger.info(
        "%s iniciado por horario/retry. business_date=%s",
        job_key,
        business_date.isoformat(),
    )

    try:
        result = run_cobranza_recurrente_job(business_date=business_date)

    except CobranzaRecurrenteNotReadyError:
        logger.warning(
            "%s todavía no está listo. Se reintentará en %s minutos.",
            job_key,
            retry_minutes,
            exc_info=True,
        )

        _schedule_retry(
            job_key=job_key,
            business_date=business_date,
            now=now,
            retry_minutes=retry_minutes,
            reason="not_ready",
        )
        return

    except Exception:  # noqa: BLE001
        logger.exception(
            "%s falló por error técnico. Se reintentará en %s minutos.",
            job_key,
            retry_minutes,
        )

        _schedule_retry(
            job_key=job_key,
            business_date=business_date,
            now=now,
            retry_minutes=retry_minutes,
            reason="technical_error",
        )
        return

    _mark_job_as_completed(job_key, business_date)

    logger.info(
        "%s finalizado OK. rows=%s files=%s uploads=%s internal_documents=%s duration=%ss",
        job_key,
        result.get("total_rows"),
        result.get("total_files"),
        (result.get("warehouse_publication") or {}).get("total_uploads"),
        (result.get("warehouse_publication") or {}).get("total_internal_documents"),
        result.get("duration_seconds"),
    )


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

            _run_cobranza_recurrente_if_due(now)

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