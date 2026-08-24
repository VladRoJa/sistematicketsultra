from __future__ import annotations

import logging
import os
import signal
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app import create_app
from app.extensions import db
from app.services.marketing_iventas_period_service import (
    resolve_iventas_month_period,
)
from app.services.marketing_iventas_run_sync_service import (
    sync_iventas_full_run,
)
from app.services.marketing_meta_run_sync_service import (
    MarketingMetaAccount,
    sync_meta_full_run,
)


LOGGER = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s [%(levelname)s] "
        "[marketing-scheduler] %(message)s"
    ),
)

DEFAULT_TIMEZONE = "America/Tijuana"
DEFAULT_RUN_HOURS = (8, 12, 16, 20)
DEFAULT_POLL_SECONDS = 60
DEFAULT_RETRY_MINUTES = 15

DEFAULT_META_ACCOUNT_BINDINGS = (
    (
        "META_ACCESS_TOKEN_CP01_CP03",
        "META_AD_ACCOUNT_CP01",
    ),
    (
        "META_ACCESS_TOKEN_CP01_CP03",
        "META_AD_ACCOUNT_CP03",
    ),
    (
        "META_ACCESS_TOKEN_ULTRAGYM2",
        "META_AD_ACCOUNT_ULTRAGYM2",
    ),
    (
        "META_ACCESS_TOKEN_ULTRAGYM3",
        "META_AD_ACCOUNT_ULTRAGYM3",
    ),
    (
        "META_ACCESS_TOKEN_ULTRAGYM4",
        "META_AD_ACCOUNT_ULTRAGYM4",
    ),
)

_SHOULD_STOP = False

_COMPLETED_SLOTS: set[tuple[date, int]] = set()
_IVENTAS_COMPLETED_SLOTS: set[tuple[date, int]] = set()
_META_COMPLETED_SLOTS: set[tuple[date, int]] = set()

_NEXT_RETRY_BY_SLOT: dict[
    tuple[date, int],
    datetime,
] = {}


@dataclass(frozen=True)
class MarketingSyncResult:
    business_date: date
    iventas_completed: bool
    meta_completed: bool

    @property
    def completed(self) -> bool:
        return (
            self.iventas_completed
            and self.meta_completed
        )


def _handle_stop(signum, frame):  # noqa: ARG001
    global _SHOULD_STOP

    LOGGER.info(
        "Señal recibida=%s. Cerrando scheduler...",
        signum,
    )
    _SHOULD_STOP = True


def _env_int(
    name: str,
    default: int,
) -> int:
    raw_value = os.getenv(name)

    if (
        raw_value is None
        or not raw_value.strip()
    ):
        return default

    try:
        return int(raw_value)
    except ValueError:
        LOGGER.warning(
            "Variable %s inválida=%r. "
            "Usando default=%s.",
            name,
            raw_value,
            default,
        )
        return default


def _timezone() -> ZoneInfo:
    timezone_name = (
        os.getenv(
            "MARKETING_SCHEDULER_TZ",
            DEFAULT_TIMEZONE,
        )
        or DEFAULT_TIMEZONE
    ).strip()

    try:
        return ZoneInfo(timezone_name)
    except Exception:  # noqa: BLE001
        LOGGER.warning(
            "Zona horaria inválida=%r. "
            "Usando %s.",
            timezone_name,
            DEFAULT_TIMEZONE,
        )
        return ZoneInfo(DEFAULT_TIMEZONE)


def _now_local() -> datetime:
    return datetime.now(_timezone())


def _parse_run_hours() -> tuple[int, ...]:
    raw_value = os.getenv(
        "MARKETING_SCHEDULER_RUN_HOURS"
    )

    if not raw_value:
        return DEFAULT_RUN_HOURS

    values: set[int] = set()

    for raw_hour in raw_value.split(","):
        clean_hour = raw_hour.strip()

        if not clean_hour:
            continue

        try:
            hour = int(clean_hour)
        except ValueError as exc:
            raise RuntimeError(
                "MARKETING_SCHEDULER_RUN_HOURS "
                f"contiene valor inválido={clean_hour!r}."
            ) from exc

        if hour < 0 or hour > 23:
            raise RuntimeError(
                "MARKETING_SCHEDULER_RUN_HOURS "
                f"fuera de rango={hour}."
            )

        values.add(hour)

    if not values:
        raise RuntimeError(
            "MARKETING_SCHEDULER_RUN_HOURS "
            "no contiene horarios válidos."
        )

    return tuple(sorted(values))


def _load_meta_accounts() -> tuple[
    MarketingMetaAccount,
    ...,
]:
    accounts: list[MarketingMetaAccount] = []

    for (
        token_env,
        account_env,
    ) in DEFAULT_META_ACCOUNT_BINDINGS:
        access_token = str(
            os.getenv(token_env) or ""
        ).strip()

        account_id = str(
            os.getenv(account_env) or ""
        ).strip()

        if not access_token:
            raise RuntimeError(
                "Falta variable de token Meta: "
                f"{token_env}."
            )

        if not account_id:
            raise RuntimeError(
                "Falta variable de cuenta Meta: "
                f"{account_env}."
            )

        accounts.append(
            MarketingMetaAccount(
                account_id=account_id,
                access_token=access_token,
            )
        )

    return tuple(accounts)


def _meta_period_key(
    business_date: date,
) -> str:
    return (
        f"META-{business_date.year:04d}-"
        f"{business_date.month:02d}"
    )


def execute_marketing_sync(
    *,
    business_date: date,
    run_iventas: bool = True,
    run_meta: bool = True,
) -> MarketingSyncResult:
    period = resolve_iventas_month_period(
        month_date=business_date,
        today=business_date,
    )

    LOGGER.info(
        "Iniciando corte Marketing. "
        "business_date=%s date_from=%s date_to=%s",
        business_date.isoformat(),
        period.date_from.isoformat(),
        period.date_to.isoformat(),
    )

    iventas_completed = not run_iventas
    meta_completed = not run_meta

    if run_iventas:
        try:
            iventas_result = sync_iventas_full_run(
                period_key=period.period_key,
                date_from=period.date_from,
                date_to=period.date_to,
            )

            iventas_completed = (
                iventas_result.status == "COMPLETED"
                and iventas_result.is_canonical
            )

            LOGGER.info(
                "iVentas terminado. "
                "run_id=%s status=%s canonical=%s "
                "branches=%s/%s",
                iventas_result.sync_run_id,
                iventas_result.status,
                iventas_result.is_canonical,
                iventas_result.branches_completed,
                iventas_result.branches_requested,
            )

        except Exception:  # noqa: BLE001
            db.session.rollback()
            LOGGER.exception(
                "iVentas falló en corte Marketing "
                "business_date=%s.",
                business_date.isoformat(),
            )

        finally:
            db.session.remove()

    if run_meta:
        try:
            meta_accounts = _load_meta_accounts()

            meta_result = sync_meta_full_run(
                period_key=_meta_period_key(
                    business_date
                ),
                date_from=period.date_from,
                date_to=period.date_to,
                accounts=meta_accounts,
            )

            meta_completed = (
                meta_result.status == "COMPLETED"
                and meta_result.is_canonical
            )

            LOGGER.info(
                "Meta terminado. "
                "run_id=%s status=%s canonical=%s "
                "accounts=%s/%s insights=%s",
                meta_result.sync_run_id,
                meta_result.status,
                meta_result.is_canonical,
                meta_result.accounts_completed,
                meta_result.accounts_requested,
                meta_result.insights_unique,
            )

        except Exception:  # noqa: BLE001
            db.session.rollback()
            LOGGER.exception(
                "Meta falló en corte Marketing "
                "business_date=%s.",
                business_date.isoformat(),
            )

        finally:
            db.session.remove()

    result = MarketingSyncResult(
        business_date=business_date,
        iventas_completed=iventas_completed,
        meta_completed=meta_completed,
    )

    LOGGER.info(
        "Corte Marketing terminado. "
        "business_date=%s "
        "iventas_completed=%s "
        "meta_completed=%s "
        "completed=%s",
        business_date.isoformat(),
        result.iventas_completed,
        result.meta_completed,
        result.completed,
    )

    return result


def _resolve_due_slot(
    *,
    now: datetime,
    run_hours: tuple[int, ...],
) -> tuple[date, int] | None:
    eligible_hours = tuple(
        hour
        for hour in run_hours
        if hour <= now.hour
    )

    if not eligible_hours:
        return None

    slot_hour = max(eligible_hours)

    slot_key = (
        now.date(),
        slot_hour,
    )

    if slot_key in _COMPLETED_SLOTS:
        return None

    next_retry_at = (
        _NEXT_RETRY_BY_SLOT.get(
            slot_key
        )
    )

    if (
        next_retry_at is not None
        and now < next_retry_at
    ):
        return None

    return slot_key


def run_scheduler_loop() -> None:
    run_hours = _parse_run_hours()

    poll_seconds = max(
        _env_int(
            "MARKETING_SCHEDULER_POLL_SECONDS",
            DEFAULT_POLL_SECONDS,
        ),
        10,
    )

    retry_minutes = max(
        _env_int(
            "MARKETING_SCHEDULER_RETRY_MINUTES",
            DEFAULT_RETRY_MINUTES,
        ),
        5,
    )

    LOGGER.info(
        "Marketing scheduler iniciado. "
        "timezone=%s run_hours=%s "
        "poll_seconds=%s retry_minutes=%s",
        _timezone().key,
        ",".join(
            str(hour)
            for hour in run_hours
        ),
        poll_seconds,
        retry_minutes,
    )

    while not _SHOULD_STOP:
        try:
            now = _now_local()

            slot_key = _resolve_due_slot(
                now=now,
                run_hours=run_hours,
            )

            if slot_key is not None:
                run_iventas = (
                    slot_key
                    not in _IVENTAS_COMPLETED_SLOTS
                )
                run_meta = (
                    slot_key
                    not in _META_COMPLETED_SLOTS
                )

                result = execute_marketing_sync(
                    business_date=slot_key[0],
                    run_iventas=run_iventas,
                    run_meta=run_meta,
                )

                if result.iventas_completed:
                    _IVENTAS_COMPLETED_SLOTS.add(
                        slot_key
                    )

                if result.meta_completed:
                    _META_COMPLETED_SLOTS.add(
                        slot_key
                    )

                if result.completed:
                    _COMPLETED_SLOTS.add(
                        slot_key
                    )
                    _NEXT_RETRY_BY_SLOT.pop(
                        slot_key,
                        None,
                    )
                else:
                    next_retry_at = (
                        now
                        + timedelta(
                            minutes=retry_minutes
                        )
                    )

                    _NEXT_RETRY_BY_SLOT[
                        slot_key
                    ] = next_retry_at

                    LOGGER.warning(
                        "Corte incompleto. "
                        "slot=%s-%02d "
                        "next_retry_at=%s",
                        slot_key[0].isoformat(),
                        slot_key[1],
                        next_retry_at.isoformat(
                            timespec="seconds"
                        ),
                    )

        except Exception:  # noqa: BLE001
            LOGGER.exception(
                "Error no controlado en ciclo "
                "de Marketing scheduler."
            )

        finally:
            db.session.remove()

        time.sleep(poll_seconds)

    LOGGER.info(
        "Marketing scheduler detenido correctamente."
    )


def main() -> None:
    signal.signal(
        signal.SIGTERM,
        _handle_stop,
    )
    signal.signal(
        signal.SIGINT,
        _handle_stop,
    )

    app = create_app()

    with app.app_context():
        run_scheduler_loop()


if __name__ == "__main__":
    main()





