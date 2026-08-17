"""Fronteras raw-first y ciclo de vida de sincronizaciones Meta."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Iterable

from app.extensions import db
from app.models import (
    MarketingMetaAdInsightORM,
    MarketingMetaRawPageORM,
    MarketingMetaSyncRunORM,
)
from app.services.marketing_meta_service import (
    MarketingMetaAdInsight,
    MarketingMetaPage,
    MarketingMetaRawPageResponse,
    normalize_meta_account_id,
)


SYNC_STATUS_RUNNING = "RUNNING"
SYNC_STATUS_COMPLETED = "COMPLETED"
SYNC_STATUS_PARTIAL = "PARTIAL"
SYNC_STATUS_FAILED = "FAILED"
TERMINAL_STATUSES = frozenset(
    {
        SYNC_STATUS_COMPLETED,
        SYNC_STATUS_PARTIAL,
        SYNC_STATUS_FAILED,
    }
)


class MarketingMetaPersistenceError(RuntimeError):
    """La evidencia Meta persistida es inconsistente."""


@dataclass(frozen=True)
class MarketingMetaStructuredPageResult:
    insights_received: int
    insights_created: int
    insights_existing: int


@dataclass(frozen=True)
class MarketingMetaRunCounters:
    accounts_completed: int
    accounts_failed: int
    pages_received: int
    insights_received: int
    insights_unique: int


@dataclass(frozen=True)
class MarketingMetaFinalizeResult:
    sync_run_id: int
    period_key: str
    status: str
    is_canonical: bool
    replaced_canonical_run_id: int | None
    was_already_finalized: bool


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _session_or_default(session: Any | None):
    return session if session is not None else db.session


def _aware_datetime(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} debe tener timezone.")
    return value


def create_meta_sync_run_running(
    *,
    period_key: str,
    date_from: date,
    date_to: date,
    accounts_requested: int,
    started_at: datetime | None = None,
    session: Any | None = None,
) -> MarketingMetaSyncRunORM:
    period_value = str(period_key or "").strip()
    if not period_value or len(period_value) > 64:
        raise ValueError(
            "period_key Meta debe tener entre 1 y 64 caracteres."
        )
    if date_from > date_to:
        raise ValueError(
            "date_from no puede ser posterior a date_to."
        )
    if (
        isinstance(accounts_requested, bool)
        or not isinstance(accounts_requested, int)
        or accounts_requested <= 0
    ):
        raise ValueError(
            "accounts_requested debe ser entero positivo."
        )

    started = _aware_datetime(
        started_at if started_at is not None else _utc_now(),
        "started_at",
    )
    session_value = _session_or_default(session)
    run = MarketingMetaSyncRunORM(
        period_key=period_value,
        date_from=date_from,
        date_to=date_to,
        started_at=started,
        finished_at=None,
        status=SYNC_STATUS_RUNNING,
        accounts_requested=accounts_requested,
        accounts_completed=0,
        accounts_failed=0,
        pages_received=0,
        insights_received=0,
        insights_unique=0,
        is_canonical=False,
    )
    session_value.add(run)
    session_value.commit()
    return run


def persist_meta_raw_page_pre_parse(
    *,
    sync_run_id: int,
    account_id: str,
    page_number: int,
    raw_response: MarketingMetaRawPageResponse,
    received_at: datetime | None = None,
    session: Any | None = None,
) -> MarketingMetaRawPageORM:
    if sync_run_id <= 0:
        raise ValueError("sync_run_id debe ser entero positivo.")
    account_value = normalize_meta_account_id(account_id)
    if page_number < 1:
        raise ValueError("page_number debe ser >= 1.")
    if not isinstance(raw_response, MarketingMetaRawPageResponse):
        raise TypeError(
            "raw_response debe ser MarketingMetaRawPageResponse."
        )
    if not 100 <= raw_response.http_status <= 599:
        raise ValueError("http_status fuera del rango HTTP.")
    if not isinstance(raw_response.raw_payload, str):
        raise TypeError("raw_payload debe ser string.")

    received = _aware_datetime(
        received_at if received_at is not None else _utc_now(),
        "received_at",
    )
    session_value = _session_or_default(session)
    existing = (
        session_value.query(MarketingMetaRawPageORM)
        .filter_by(
            sync_run_id=sync_run_id,
            account_id=account_value,
            page_number=page_number,
        )
        .first()
    )
    if existing is not None:
        if (
            existing.request_cursor != raw_response.request_cursor
            or existing.http_status != raw_response.http_status
            or existing.payload_json != raw_response.raw_payload
        ):
            raise MarketingMetaPersistenceError(
                "La página Meta ya existe con contenido HTTP diferente."
            )
        return existing

    raw_page = MarketingMetaRawPageORM(
        sync_run_id=sync_run_id,
        account_id=account_value,
        page_number=page_number,
        request_cursor=raw_response.request_cursor,
        next_cursor=None,
        has_more=None,
        rows_count=None,
        http_status=raw_response.http_status,
        payload_json=raw_response.raw_payload,
        received_at=received,
    )
    session_value.add(raw_page)
    session_value.commit()
    return raw_page


def apply_meta_raw_page_parse_metadata(
    *,
    raw_page_id: int,
    page: MarketingMetaPage,
    session: Any | None = None,
) -> MarketingMetaRawPageORM:
    if raw_page_id <= 0:
        raise ValueError("raw_page_id debe ser entero positivo.")
    if not isinstance(page, MarketingMetaPage):
        raise TypeError("page debe ser MarketingMetaPage.")

    session_value = _session_or_default(session)
    raw_page = session_value.get(
        MarketingMetaRawPageORM,
        raw_page_id,
    )
    if raw_page is None:
        raise MarketingMetaPersistenceError(
            "No existe la raw page Meta indicada."
        )
    if (
        raw_page.request_cursor != page.request_cursor
        or raw_page.http_status != page.http_status
        or raw_page.payload_json != page.raw_payload
    ):
        raise MarketingMetaPersistenceError(
            "La página parseada no corresponde al raw persistido."
        )

    rows_count = len(page.insights)
    if raw_page.has_more is not None:
        if (
            raw_page.has_more != page.has_more
            or raw_page.next_cursor != page.next_cursor
            or raw_page.rows_count != rows_count
        ):
            raise MarketingMetaPersistenceError(
                "La metadata Meta ya existe con valores diferentes."
            )
        return raw_page

    if raw_page.next_cursor is not None or raw_page.rows_count is not None:
        raise MarketingMetaPersistenceError(
            "La raw page Meta tiene metadata parcial."
        )

    raw_page.next_cursor = page.next_cursor
    raw_page.has_more = page.has_more
    raw_page.rows_count = rows_count
    session_value.commit()
    return raw_page


def persist_meta_structured_page(
    *,
    sync_run_id: int,
    raw_page_id: int,
    insights: Iterable[MarketingMetaAdInsight],
    session: Any | None = None,
) -> MarketingMetaStructuredPageResult:
    if sync_run_id <= 0 or raw_page_id <= 0:
        raise ValueError(
            "sync_run_id y raw_page_id deben ser positivos."
        )
    normalized = tuple(insights)
    if any(
        not isinstance(row, MarketingMetaAdInsight)
        for row in normalized
    ):
        raise TypeError(
            "insights debe contener MarketingMetaAdInsight."
        )

    identities = [
        (
            row.account_id,
            row.ad_id,
            row.date_start,
            row.date_stop,
        )
        for row in normalized
    ]
    if len(identities) != len(set(identities)):
        raise MarketingMetaPersistenceError(
            "La página Meta contiene insights duplicados."
        )

    session_value = _session_or_default(session)
    raw_page = session_value.get(MarketingMetaRawPageORM, raw_page_id)
    if raw_page is None or int(raw_page.sync_run_id) != sync_run_id:
        raise MarketingMetaPersistenceError(
            "La raw page Meta no pertenece al sync run."
        )
    if raw_page.rows_count is None:
        raise MarketingMetaPersistenceError(
            "La raw page Meta debe parsearse antes de estructurarla."
        )
    if int(raw_page.rows_count) != len(normalized):
        raise MarketingMetaPersistenceError(
            "El número de insights no coincide con la raw page."
        )

    created = 0
    existing_count = 0
    try:
        for insight in normalized:
            if insight.account_id != raw_page.account_id:
                raise MarketingMetaPersistenceError(
                    "El insight pertenece a otra cuenta Meta."
                )
            existing = (
                session_value.query(MarketingMetaAdInsightORM)
                .filter_by(
                    sync_run_id=sync_run_id,
                    account_id=insight.account_id,
                    ad_id=insight.ad_id,
                    date_start=insight.date_start,
                    date_stop=insight.date_stop,
                )
                .first()
            )
            if existing is not None:
                if existing.row_hash != insight.row_hash:
                    raise MarketingMetaPersistenceError(
                        "El insight Meta ya existe con datos diferentes."
                    )
                existing_count += 1
                continue

            session_value.add(
                MarketingMetaAdInsightORM(
                    sync_run_id=sync_run_id,
                    raw_page_id=raw_page_id,
                    account_id=insight.account_id,
                    account_name=insight.account_name,
                    campaign_id=insight.campaign_id,
                    campaign_name=insight.campaign_name,
                    adset_id=insight.adset_id,
                    adset_name=insight.adset_name,
                    ad_id=insight.ad_id,
                    ad_name=insight.ad_name,
                    date_start=insight.date_start,
                    date_stop=insight.date_stop,
                    spend=insight.spend,
                    reach=insight.reach,
                    impressions=insight.impressions,
                    clicks=insight.clicks,
                    actions_json=[
                        dict(action)
                        for action in insight.actions
                    ],
                    row_hash=insight.row_hash,
                )
            )
            created += 1

        if created:
            session_value.commit()

        return MarketingMetaStructuredPageResult(
            insights_received=len(normalized),
            insights_created=created,
            insights_existing=existing_count,
        )
    except Exception:
        session_value.rollback()
        raise


def _validate_counters(
    counters: MarketingMetaRunCounters,
    accounts_requested: int,
) -> None:
    if not isinstance(counters, MarketingMetaRunCounters):
        raise TypeError("counters debe ser MarketingMetaRunCounters.")
    for field_name in counters.__dataclass_fields__:
        value = getattr(counters, field_name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(
                f"{field_name} debe ser entero no negativo."
            )
    if (
        counters.accounts_completed + counters.accounts_failed
        != accounts_requested
    ):
        raise ValueError(
            "La contabilidad de cuentas no cubre accounts_requested."
        )
    if counters.insights_unique > counters.insights_received:
        raise ValueError(
            "insights_unique no puede superar insights_received."
        )


def _matches_terminal_state(
    run: MarketingMetaSyncRunORM,
    status: str,
    counters: MarketingMetaRunCounters,
    make_canonical: bool,
) -> bool:
    return (
        run.status == status
        and bool(run.is_canonical) == make_canonical
        and run.finished_at is not None
        and all(
            getattr(run, field_name) == getattr(counters, field_name)
            for field_name in counters.__dataclass_fields__
        )
    )


def finalize_meta_sync_run(
    *,
    sync_run_id: int,
    status: str,
    counters: MarketingMetaRunCounters,
    make_canonical: bool = False,
    finished_at: datetime | None = None,
    session: Any | None = None,
) -> MarketingMetaFinalizeResult:
    status_value = str(status or "").strip().upper()
    if status_value not in TERMINAL_STATUSES:
        raise ValueError("Estado terminal Meta inválido.")
    if not isinstance(make_canonical, bool):
        raise TypeError("make_canonical debe ser bool.")

    finished = _aware_datetime(
        finished_at if finished_at is not None else _utc_now(),
        "finished_at",
    )
    session_value = _session_or_default(session)
    replaced_canonical_run_id = None

    try:
        run = session_value.get(MarketingMetaSyncRunORM, sync_run_id)
        if run is None:
            raise MarketingMetaPersistenceError(
                "No existe el sync run Meta."
            )
        _validate_counters(counters, int(run.accounts_requested))
        if finished < run.started_at:
            raise ValueError(
                "finished_at no puede ser anterior a started_at."
            )
        completed_is_valid = (
            counters.accounts_completed == int(run.accounts_requested)
            and counters.accounts_failed == 0
        )
        if status_value == SYNC_STATUS_COMPLETED and not completed_is_valid:
            raise MarketingMetaPersistenceError(
                "COMPLETED requiere todas las cuentas completas."
            )
        if make_canonical and (
            status_value != SYNC_STATUS_COMPLETED
            or not completed_is_valid
        ):
            raise MarketingMetaPersistenceError(
                "Sólo un run Meta COMPLETED puede ser canónico."
            )

        if run.status != SYNC_STATUS_RUNNING:
            if _matches_terminal_state(
                run,
                status_value,
                counters,
                make_canonical,
            ):
                return MarketingMetaFinalizeResult(
                    sync_run_id=int(run.id),
                    period_key=run.period_key,
                    status=run.status,
                    is_canonical=bool(run.is_canonical),
                    replaced_canonical_run_id=None,
                    was_already_finalized=True,
                )
            raise MarketingMetaPersistenceError(
                "El sync run Meta ya fue finalizado de otra forma."
            )

        if make_canonical:
            previous_rows = [
                row
                for row in (
                    session_value.query(MarketingMetaSyncRunORM)
                    .filter_by(
                        period_key=run.period_key,
                        is_canonical=True,
                    )
                    .all()
                )
                if int(row.id) != int(run.id)
            ]
            if len(previous_rows) > 1:
                raise MarketingMetaPersistenceError(
                    "Existe más de un canónico Meta previo."
                )
            if previous_rows:
                previous = previous_rows[0]
                previous.is_canonical = False
                replaced_canonical_run_id = int(previous.id)
                session_value.flush()

        for field_name in counters.__dataclass_fields__:
            setattr(run, field_name, getattr(counters, field_name))
        run.status = status_value
        run.finished_at = finished
        run.is_canonical = make_canonical
        session_value.commit()

        return MarketingMetaFinalizeResult(
            sync_run_id=int(run.id),
            period_key=run.period_key,
            status=run.status,
            is_canonical=bool(run.is_canonical),
            replaced_canonical_run_id=replaced_canonical_run_id,
            was_already_finalized=False,
        )
    except Exception:
        session_value.rollback()
        raise
