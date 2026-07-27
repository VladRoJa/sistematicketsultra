from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import (
    date,
    datetime,
    time as dt_time,
    timezone,
)
from typing import Any, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

from app import create_app, db
from app.models.routine_control import (
    RoutineControlPipelineRunORM,
)
from app.routine_control.pipeline.automated_pipeline_service import (
    run_automated_routine_control_pipeline,
)


LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "America/Tijuana"
DEFAULT_DAILY_TIME = "08:30"
DEFAULT_POLL_SECONDS = 60

SCHEDULED_GENERATION_MODE = "SCHEDULED"
SCHEDULER_TRIGGER_SOURCE = (
    "ROUTINE_CONTROL_SCHEDULER"
)


@dataclass(frozen=True)
class RoutineControlSchedulerDecision:
    business_date: date
    date_from: date
    date_to: date
    observed_at_utc: datetime
    reason: str


def _env_bool(
    name: str,
    default: bool,
) -> bool:
    raw_value = os.getenv(name)

    if raw_value is None or raw_value.strip() == "":
        return default

    normalized = raw_value.strip().lower()

    if normalized in {"1", "true", "yes", "on"}:
        return True

    if normalized in {"0", "false", "no", "off"}:
        return False

    LOGGER.warning(
        "Valor booleano inválido para %s=%r. "
        "Usando default=%s.",
        name,
        raw_value,
        default,
    )

    return default


def _env_int(
    name: str,
    default: int,
) -> int:
    raw_value = os.getenv(name)

    if raw_value is None or raw_value.strip() == "":
        return default

    try:
        parsed = int(raw_value)
    except ValueError:
        LOGGER.warning(
            "Valor entero inválido para %s=%r. "
            "Usando default=%s.",
            name,
            raw_value,
            default,
        )
        return default

    if parsed < 1:
        LOGGER.warning(
            "Valor fuera de rango para %s=%r. "
            "Usando default=%s.",
            name,
            raw_value,
            default,
        )
        return default

    return parsed


def _resolve_timezone() -> ZoneInfo:
    timezone_name = (
        os.getenv("ROUTINE_CONTROL_TIMEZONE")
        or DEFAULT_TIMEZONE
    ).strip()

    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        LOGGER.warning(
            "Timezone inválido %r. Usando %s.",
            timezone_name,
            DEFAULT_TIMEZONE,
        )
        return ZoneInfo(DEFAULT_TIMEZONE)


def _parse_daily_time(value: str) -> dt_time:
    normalized = str(value or "").strip()

    try:
        hour_text, minute_text = normalized.split(
            ":",
            maxsplit=1,
        )
        hour = int(hour_text)
        minute = int(minute_text)
        return dt_time(hour=hour, minute=minute)
    except (TypeError, ValueError):
        raise ValueError(
            "ROUTINE_CONTROL_DAILY_TIME debe usar HH:MM."
        )


def _resolve_daily_time() -> dt_time:
    raw_value = (
        os.getenv("ROUTINE_CONTROL_DAILY_TIME")
        or DEFAULT_DAILY_TIME
    )

    try:
        return _parse_daily_time(raw_value)
    except ValueError:
        LOGGER.warning(
            "Hora diaria inválida %r. Usando %s.",
            raw_value,
            DEFAULT_DAILY_TIME,
        )
        return _parse_daily_time(DEFAULT_DAILY_TIME)


def _has_successful_scheduled_run(
    *,
    business_date: date,
) -> bool:
    statement = (
        select(RoutineControlPipelineRunORM.id)
        .where(
            RoutineControlPipelineRunORM.business_date
            == business_date,
            RoutineControlPipelineRunORM.generation_mode
            == SCHEDULED_GENERATION_MODE,
            RoutineControlPipelineRunORM.trigger_source
            == SCHEDULER_TRIGGER_SOURCE,
            RoutineControlPipelineRunORM.status
            == "SUCCESS",
        )
        .limit(1)
    )

    return (
        db.session.execute(statement).scalar_one_or_none()
        is not None
    )


def decide_routine_control_scheduler_action(
    now_local: datetime,
    *,
    scheduled_time: dt_time,
    has_successful_run: bool,
    already_attempted: bool,
) -> RoutineControlSchedulerDecision | None:
    if (
        now_local.tzinfo is None
        or now_local.utcoffset() is None
    ):
        raise ValueError(
            "now_local debe incluir timezone."
        )

    current_time = dt_time(
        hour=now_local.hour,
        minute=now_local.minute,
        second=now_local.second,
    )

    if current_time < scheduled_time:
        return None

    if has_successful_run or already_attempted:
        return None

    business_date = now_local.date()

    return RoutineControlSchedulerDecision(
        business_date=business_date,
        date_from=business_date.replace(day=1),
        date_to=business_date,
        observed_at_utc=now_local.astimezone(
            timezone.utc
        ),
        reason="daily_cutoff_pending",
    )


def execute_routine_control_scheduler_decision(
    decision: RoutineControlSchedulerDecision,
    *,
    pipeline_service: Callable[..., Any] = (
        run_automated_routine_control_pipeline
    ),
) -> Any:
    LOGGER.info(
        "Ejecutando scheduler Control de Rutinas: "
        "business_date=%s date_from=%s date_to=%s",
        decision.business_date.isoformat(),
        decision.date_from.isoformat(),
        decision.date_to.isoformat(),
    )

    return pipeline_service(
        date_from=decision.date_from,
        date_to=decision.date_to,
        observed_at_utc=decision.observed_at_utc,
        generation_mode=SCHEDULED_GENERATION_MODE,
        trigger_source=SCHEDULER_TRIGGER_SOURCE,
        headless=True,
    )


def run_scheduler_loop() -> None:
    enabled = _env_bool(
        "ROUTINE_CONTROL_SCHEDULER_ENABLED",
        True,
    )
    poll_seconds = _env_int(
        "ROUTINE_CONTROL_WORKER_POLL_SECONDS",
        DEFAULT_POLL_SECONDS,
    )
    scheduler_timezone = _resolve_timezone()
    scheduled_time = _resolve_daily_time()

    LOGGER.info(
        "Routine Control scheduler iniciado. "
        "enabled=%s timezone=%s daily_time=%s "
        "poll_seconds=%s",
        enabled,
        scheduler_timezone.key,
        scheduled_time.strftime("%H:%M"),
        poll_seconds,
    )

    app = create_app()
    last_attempted_date: date | None = None

    with app.app_context():
        while True:
            try:
                if enabled:
                    now_local = datetime.now(
                        scheduler_timezone
                    )
                    business_date = now_local.date()

                    has_successful_run = (
                        _has_successful_scheduled_run(
                            business_date=business_date
                        )
                    )

                    decision = (
                        decide_routine_control_scheduler_action(
                            now_local,
                            scheduled_time=scheduled_time,
                            has_successful_run=(
                                has_successful_run
                            ),
                            already_attempted=(
                                last_attempted_date
                                == business_date
                            ),
                        )
                    )

                    if decision is not None:
                        last_attempted_date = (
                            decision.business_date
                        )

                        try:
                            result = (
                                execute_routine_control_scheduler_decision(
                                    decision
                                )
                            )

                            LOGGER.info(
                                "Routine Control scheduler terminó. "
                                "business_date=%s status=%s "
                                "succeeded=%s error_code=%s",
                                decision.business_date.isoformat(),
                                getattr(result, "status", None),
                                getattr(result, "succeeded", None),
                                getattr(
                                    result,
                                    "error_code",
                                    None,
                                ),
                            )
                        except Exception:
                            LOGGER.exception(
                                "Routine Control scheduler falló. "
                                "business_date=%s",
                                decision.business_date.isoformat(),
                            )
            finally:
                db.session.remove()

            time.sleep(poll_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_scheduler_loop()
