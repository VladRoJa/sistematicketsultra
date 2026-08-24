#   backend\app\warehouse\scheduler\track_scheduler_worker.py


from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta
from zoneinfo import ZoneInfo

from app import create_app, db
from app.warehouse.services.track_daily_pipeline_service import (
    run_requested_track_canonical_close,
    run_track_daily_pipeline_for_date,
)
from app.warehouse.services.track_daily_version_service import (
    claim_next_pending_track_canonical_close,
    get_current_track_daily_version,
)
from app.warehouse.services.warehouse_retention_service import (
    purge_venta_total_non_canonical_snapshots,
)

LOGGER = logging.getLogger(__name__)

TRACK_TIMEZONE = ZoneInfo("America/Tijuana")

DEFAULT_POLL_INTERVAL_SECONDS = 60
DEFAULT_PREVIEW_START_HOUR = 5
DEFAULT_PREVIEW_END_HOUR = 23
DEFAULT_NIGHTLY_BASE_HOUR = 23
DEFAULT_NIGHTLY_BASE_MINUTE = 30
DEFAULT_NIGHTLY_RETRY_HOUR = 0
DEFAULT_NIGHTLY_RETRY_MINUTE = 30
DEFAULT_WAREHOUSE_RETENTION_HOUR = 1
DEFAULT_WAREHOUSE_RETENTION_MINUTE = 10
DEFAULT_WAREHOUSE_RETENTION_DAYS = 7
DEFAULT_WAREHOUSE_RETENTION_BATCH_LIMIT = 100
DEFAULT_WAREHOUSE_RETENTION_MAX_BATCHES = 20


@dataclass(frozen=True)
class TrackSchedulerDecision:
    action: str
    track_date: date
    reason: str


def _now_tijuana() -> datetime:
    return datetime.now(TRACK_TIMEZONE)


def _env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)

    if raw_value is None or raw_value.strip() == "":
        return default

    try:
        return int(raw_value)
    except ValueError:
        LOGGER.warning(
            "Valor inválido para %s=%r. Usando default=%s.",
            name,
            raw_value,
            default,
        )
        return default


def _is_top_of_hour(value: datetime) -> bool:
    return value.minute == 0


def _is_exact_minute(value: datetime, *, hour: int, minute: int) -> bool:
    return value.hour == hour and value.minute == minute


def _has_success_current_version(*, track_date: date, version_type: str) -> bool:
    version = get_current_track_daily_version(
        track_date=track_date,
        version_type=version_type,
    )

    return bool(version and version.status == "success")


def _has_failed_current_version(*, track_date: date, version_type: str) -> bool:
    version = get_current_track_daily_version(
        track_date=track_date,
        version_type=version_type,
    )

    return bool(version and version.status == "failed")


def decide_track_scheduler_action(now_local: datetime) -> TrackSchedulerDecision | None:
    preview_start_hour = _env_int(
        "TRACK_PREVIEW_START_HOUR",
        DEFAULT_PREVIEW_START_HOUR,
    )
    preview_end_hour = _env_int(
        "TRACK_PREVIEW_END_HOUR",
        DEFAULT_PREVIEW_END_HOUR,
    )
    nightly_base_hour = _env_int(
        "TRACK_NIGHTLY_BASE_HOUR",
        DEFAULT_NIGHTLY_BASE_HOUR,
    )
    nightly_base_minute = _env_int(
        "TRACK_NIGHTLY_BASE_MINUTE",
        DEFAULT_NIGHTLY_BASE_MINUTE,
    )
    nightly_retry_hour = _env_int(
        "TRACK_NIGHTLY_RETRY_HOUR",
        DEFAULT_NIGHTLY_RETRY_HOUR,
    )
    nightly_retry_minute = _env_int(
        "TRACK_NIGHTLY_RETRY_MINUTE",
        DEFAULT_NIGHTLY_RETRY_MINUTE,
    )

    today = now_local.date()

    if (
        preview_start_hour <= now_local.hour <= preview_end_hour
        and _is_top_of_hour(now_local)
    ):
        return TrackSchedulerDecision(
            action="preview_operativo",
            track_date=today,
            reason="hourly_preview_window",
        )

    if _is_exact_minute(
        now_local,
        hour=nightly_base_hour,
        minute=nightly_base_minute,
    ):
        return TrackSchedulerDecision(
            action="base_nocturna_canonica",
            track_date=today,
            reason="nightly_base_window",
        )

    if _is_exact_minute(
        now_local,
        hour=nightly_retry_hour,
        minute=nightly_retry_minute,
    ):
        previous_day = today - timedelta(days=1)

        if _has_failed_current_version(
            track_date=previous_day,
            version_type="base_nocturna_canonica",
        ) and not _has_success_current_version(
            track_date=previous_day,
            version_type="base_nocturna_canonica",
        ):
            return TrackSchedulerDecision(
                action="base_nocturna_retry",
                track_date=previous_day,
                reason="nightly_base_retry_after_failure",
            )

    return None


def execute_track_scheduler_decision(decision: TrackSchedulerDecision) -> dict:
    LOGGER.info(
        "Ejecutando decisión scheduler Track: action=%s track_date=%s reason=%s",
        decision.action,
        decision.track_date.isoformat(),
        decision.reason,
    )

    if decision.action == "preview_operativo":
        return run_track_daily_pipeline_for_date(
            business_date=decision.track_date,
            generation_mode="manual_preview",
            requested_by="track_scheduler",
            trigger_source="scheduler_hourly_preview",
        )

    if decision.action == "base_nocturna_canonica":
        return run_track_daily_pipeline_for_date(
            business_date=decision.track_date,
            generation_mode="official_closed_day",
            requested_by="track_scheduler",
            trigger_source="scheduler_nightly_base",
        )

    if decision.action == "base_nocturna_retry":
        return run_track_daily_pipeline_for_date(
            business_date=decision.track_date,
            generation_mode="official_closed_day",
            requested_by="track_scheduler",
            trigger_source="scheduler_nightly_retry",
        )

    raise RuntimeError(f"Acción scheduler no soportada: {decision.action!r}")


def execute_pending_track_canonical_close_request() -> dict | None:
    """
    Reclama y ejecuta como máximo una solicitud explícita pendiente.

    La selección/claim ocurre en track_daily_version_service con
    FOR UPDATE SKIP LOCKED. El trabajo largo recibe el version_id
    persistido y nunca selecciona fechas históricas por su cuenta.
    """
    request_version = claim_next_pending_track_canonical_close(
        auto_commit=True,
    )

    if request_version is None:
        return None

    request_version_id = int(request_version.id)
    request_track_date = request_version.track_date

    LOGGER.info(
        "Track scheduler reclamó cierre canónico manual: "
        "version_id=%s track_date=%s requested_by=%s",
        request_version_id,
        request_track_date.isoformat(),
        request_version.requested_by,
    )

    return run_requested_track_canonical_close(
        track_daily_version_id=request_version_id,
    )

def execute_warehouse_retention() -> dict:
    retention_days = _env_int(
        "WAREHOUSE_RETENTION_DAYS",
        DEFAULT_WAREHOUSE_RETENTION_DAYS,
    )
    batch_limit = _env_int(
        "WAREHOUSE_RETENTION_BATCH_LIMIT",
        DEFAULT_WAREHOUSE_RETENTION_BATCH_LIMIT,
    )
    max_batches = _env_int(
        "WAREHOUSE_RETENTION_MAX_BATCHES",
        DEFAULT_WAREHOUSE_RETENTION_MAX_BATCHES,
    )

    LOGGER.info(
        "Ejecutando retención Warehouse: report_type=venta_total retention_days=%s batch_limit=%s max_batches=%s",
        retention_days,
        batch_limit,
        max_batches,
    )

    result = purge_venta_total_non_canonical_snapshots(
        retention_days=retention_days,
        batch_limit=batch_limit,
        max_batches=max_batches,
        dry_run=False,
    )

    LOGGER.info(
        "Retención Warehouse terminó: report_type=%s deleted_snapshots=%s deleted_rows=%s batches=%s cutoff_date=%s",
        result.get("report_type_key"),
        result.get("deleted_snapshots"),
        result.get("deleted_rows"),
        result.get("batches"),
        result.get("cutoff_date"),
    )

    return result

def _should_run_warehouse_retention(
    *,
    now_local: datetime,
    last_run_date: date | None,
) -> bool:
    retention_hour = _env_int(
        "WAREHOUSE_RETENTION_HOUR",
        DEFAULT_WAREHOUSE_RETENTION_HOUR,
    )
    retention_minute = _env_int(
        "WAREHOUSE_RETENTION_MINUTE",
        DEFAULT_WAREHOUSE_RETENTION_MINUTE,
    )

    return (
        _is_exact_minute(
            now_local,
            hour=retention_hour,
            minute=retention_minute,
        )
        and last_run_date != now_local.date()
    )


def run_scheduler_loop() -> None:
    poll_interval_seconds = _env_int(
        "TRACK_SCHEDULER_POLL_INTERVAL_SECONDS",
        DEFAULT_POLL_INTERVAL_SECONDS,
    )

    LOGGER.info(
        "Track scheduler iniciado. timezone=%s poll_interval_seconds=%s",
        TRACK_TIMEZONE.key,
        poll_interval_seconds,
    )

    app = create_app()
    last_warehouse_retention_run_date: date | None = None

    with app.app_context():
        while True:
            try:
                now_local = _now_tijuana()
                decision = decide_track_scheduler_action(now_local)

                if decision is not None:
                    try:
                        result = execute_track_scheduler_decision(decision)
                        LOGGER.info(
                            "Track scheduler terminó action=%s track_date=%s result_status=%s",
                            decision.action,
                            decision.track_date.isoformat(),
                            result.get("status") if isinstance(result, dict) else None,
                        )
                    except Exception:
                        LOGGER.exception(
                            "Track scheduler falló action=%s track_date=%s",
                            decision.action,
                            decision.track_date.isoformat(),
                        )
                if _should_run_warehouse_retention(
                    now_local=now_local,
                    last_run_date=(
                        last_warehouse_retention_run_date
                    ),
                ):
                    try:
                        execute_warehouse_retention()
                        last_warehouse_retention_run_date = (
                            now_local.date()
                        )
                    except Exception:
                        LOGGER.exception(
                            "Retención Warehouse falló "
                            "para fecha local=%s",
                            now_local.date().isoformat(),
                        )

                if decision is None:
                    try:
                        close_result = (
                            execute_pending_track_canonical_close_request()
                        )

                        if close_result is not None:
                            LOGGER.info(
                                "Track scheduler terminó cierre canónico "
                                "manual: version_id=%s track_date=%s "
                                "result_status=%s",
                                (
                                    close_result.get(
                                        "track_daily_version",
                                        {},
                                    ).get("id")
                                    if isinstance(close_result, dict)
                                    else None
                                ),
                                (
                                    close_result.get("track_date")
                                    if isinstance(close_result, dict)
                                    else None
                                ),
                                (
                                    close_result.get("status")
                                    if isinstance(close_result, dict)
                                    else None
                                ),
                            )
                    except Exception:
                        LOGGER.exception(
                            "Track scheduler falló procesando "
                            "solicitud manual de cierre canónico."
                        )

            finally:
                db.session.remove()

            time.sleep(poll_interval_seconds)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_scheduler_loop()