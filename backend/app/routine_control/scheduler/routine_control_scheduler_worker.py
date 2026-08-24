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
from app.warehouse.services.scheduler_priority_service import (
    get_secondary_job_block_reason,
)


LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "America/Tijuana"
DEFAULT_RUN_TIMES = (
    "09:20",
    "13:20",
    "17:20",
    "21:20",
)
DEFAULT_POLL_SECONDS = 60

SCHEDULED_GENERATION_MODE = "SCHEDULED"
SCHEDULER_TRIGGER_SOURCE = (
    "ROUTINE_CONTROL_SCHEDULER"
)

RoutineControlSlotKey = tuple[date, int, int]


@dataclass(frozen=True)
class RoutineControlSchedulerDecision:
    business_date: date
    date_from: date
    date_to: date
    observed_at_utc: datetime
    scheduled_time: dt_time
    slot_key: RoutineControlSlotKey
    trigger_source: str
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
            "El horario de Routine Control debe usar HH:MM."
        )


def _resolve_run_times() -> tuple[dt_time, ...]:
    raw_value = str(
        os.getenv("ROUTINE_CONTROL_RUN_TIMES")
        or ""
    ).strip()

    if raw_value:
        try:
            values = {
                _parse_daily_time(item.strip())
                for item in raw_value.split(",")
                if item.strip()
            }

            if not values:
                raise ValueError(
                    "No contiene horarios."
                )

            return tuple(sorted(values))

        except ValueError:
            LOGGER.warning(
                "ROUTINE_CONTROL_RUN_TIMES inválido=%r. "
                "Usando defaults=%s.",
                raw_value,
                ",".join(DEFAULT_RUN_TIMES),
            )

            return tuple(
                _parse_daily_time(value)
                for value in DEFAULT_RUN_TIMES
            )

    legacy_value = str(
        os.getenv("ROUTINE_CONTROL_DAILY_TIME")
        or ""
    ).strip()

    if legacy_value:
        try:
            return (
                _parse_daily_time(legacy_value),
            )
        except ValueError:
            LOGGER.warning(
                "ROUTINE_CONTROL_DAILY_TIME inválido=%r. "
                "Usando nuevos defaults=%s.",
                legacy_value,
                ",".join(DEFAULT_RUN_TIMES),
            )

    return tuple(
        _parse_daily_time(value)
        for value in DEFAULT_RUN_TIMES
    )


def _resolve_due_scheduled_time(
    *,
    now_local: datetime,
    run_times: tuple[dt_time, ...],
) -> dt_time | None:
    current_time = dt_time(
        hour=now_local.hour,
        minute=now_local.minute,
        second=now_local.second,
    )

    eligible = tuple(
        scheduled_time
        for scheduled_time in run_times
        if scheduled_time <= current_time
    )

    if not eligible:
        return None

    return max(eligible)


def _build_slot_trigger_source(
    scheduled_time: dt_time,
) -> str:
    return (
        f"{SCHEDULER_TRIGGER_SOURCE}_"
        f"{scheduled_time.hour:02d}_"
        f"{scheduled_time.minute:02d}"
    )


def _build_slot_key(
    *,
    business_date: date,
    scheduled_time: dt_time,
) -> RoutineControlSlotKey:
    return (
        business_date,
        scheduled_time.hour,
        scheduled_time.minute,
    )

def _has_successful_scheduled_run(
    *,
    business_date: date,
    trigger_source: str,
) -> bool:
    statement = (
        select(RoutineControlPipelineRunORM.id)
        .where(
            RoutineControlPipelineRunORM.business_date
            == business_date,
            RoutineControlPipelineRunORM.generation_mode
            == SCHEDULED_GENERATION_MODE,
            RoutineControlPipelineRunORM.trigger_source
            == trigger_source,
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
    trigger_source = _build_slot_trigger_source(
        scheduled_time
    )

    return RoutineControlSchedulerDecision(
        business_date=business_date,
        date_from=business_date.replace(day=1),
        date_to=business_date,
        observed_at_utc=now_local.astimezone(
            timezone.utc
        ),
        scheduled_time=scheduled_time,
        slot_key=_build_slot_key(
            business_date=business_date,
            scheduled_time=scheduled_time,
        ),
        trigger_source=trigger_source,
        reason="scheduled_slot_pending",
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
        "business_date=%s slot=%s "
        "date_from=%s date_to=%s",
        decision.business_date.isoformat(),
        decision.scheduled_time.strftime("%H:%M"),
        decision.date_from.isoformat(),
        decision.date_to.isoformat(),
    )

    return pipeline_service(
        date_from=decision.date_from,
        date_to=decision.date_to,
        observed_at_utc=decision.observed_at_utc,
        generation_mode=SCHEDULED_GENERATION_MODE,
        trigger_source=decision.trigger_source,
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
    run_times = _resolve_run_times()

    LOGGER.info(
        "Routine Control scheduler iniciado. "
        "enabled=%s timezone=%s run_times=%s "
        "poll_seconds=%s",
        enabled,
        scheduler_timezone.key,
        ",".join(
            value.strftime("%H:%M")
            for value in run_times
        ),
        poll_seconds,
    )

    app = create_app()
    attempted_slots: set[RoutineControlSlotKey] = set()

    with app.app_context():
        while True:
            try:
                if enabled:
                    now_local = datetime.now(
                        scheduler_timezone
                    )
                    business_date = now_local.date()

                    attempted_slots = {
                        slot_key
                        for slot_key in attempted_slots
                        if slot_key[0] == business_date
                    }

                    scheduled_time = (
                        _resolve_due_scheduled_time(
                            now_local=now_local,
                            run_times=run_times,
                        )
                    )

                    if scheduled_time is not None:
                        block_reason = (
                            get_secondary_job_block_reason(
                                now_local
                            )
                        )

                        if block_reason is None:
                            trigger_source = (
                                _build_slot_trigger_source(
                                    scheduled_time
                                )
                            )

                            slot_key = _build_slot_key(
                                business_date=business_date,
                                scheduled_time=scheduled_time,
                            )

                            has_successful_run = (
                                _has_successful_scheduled_run(
                                    business_date=business_date,
                                    trigger_source=trigger_source,
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
                                        slot_key
                                        in attempted_slots
                                    ),
                                )
                            )

                            if decision is not None:
                                attempted_slots.add(
                                    decision.slot_key
                                )

                                try:
                                    result = (
                                        execute_routine_control_scheduler_decision(
                                            decision
                                        )
                                    )

                                    LOGGER.info(
                                        "Routine Control scheduler terminó. "
                                        "business_date=%s slot=%s "
                                        "status=%s succeeded=%s "
                                        "error_code=%s",
                                        decision.business_date.isoformat(),
                                        decision.scheduled_time.strftime(
                                            "%H:%M"
                                        ),
                                        getattr(
                                            result,
                                            "status",
                                            None,
                                        ),
                                        getattr(
                                            result,
                                            "succeeded",
                                            None,
                                        ),
                                        getattr(
                                            result,
                                            "error_code",
                                            None,
                                        ),
                                    )
                                except Exception:
                                    LOGGER.exception(
                                        "Routine Control scheduler falló. "
                                        "business_date=%s slot=%s",
                                        decision.business_date.isoformat(),
                                        decision.scheduled_time.strftime(
                                            "%H:%M"
                                        ),
                                    )
                        else:
                            LOGGER.debug(
                                "Routine Control diferido por "
                                "prioridad Track. reason=%s now=%s",
                                block_reason,
                                now_local.isoformat(
                                    timespec="seconds"
                                ),
                            )
            finally:
                db.session.remove()

            time.sleep(poll_seconds)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_scheduler_loop()
