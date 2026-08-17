"""Orquestación explícita de una corrida Meta Ads raw-first."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
import logging
from typing import Any, Iterable

from app.extensions import db
from app.integrations.meta import (
    MetaInsightsClient,
    MetaInsightsClientError,
)
from app.services.marketing_meta_persistence_service import (
    MarketingMetaPersistenceError,
    MarketingMetaRunCounters,
    SYNC_STATUS_COMPLETED,
    SYNC_STATUS_FAILED,
    SYNC_STATUS_PARTIAL,
    apply_meta_raw_page_parse_metadata,
    create_meta_sync_run_running,
    finalize_meta_sync_run,
    persist_meta_raw_page_pre_parse,
    persist_meta_structured_page,
)
from app.services.marketing_meta_service import (
    MarketingMetaParseError,
    normalize_meta_account_id,
    parse_meta_raw_page,
)


logger = logging.getLogger(__name__)


class MarketingMetaRunSyncError(RuntimeError):
    """La corrida Meta no puede continuar de forma consistente."""


@dataclass(frozen=True)
class MarketingMetaAccount:
    account_id: str
    access_token: str = field(repr=False)


@dataclass(frozen=True)
class MarketingMetaAccountFailure:
    account_id: str
    error_type: str


@dataclass(frozen=True)
class MarketingMetaRunSyncResult:
    sync_run_id: int
    period_key: str
    status: str
    is_canonical: bool
    accounts_requested: int
    accounts_completed: int
    accounts_failed: int
    pages_received: int
    insights_received: int
    insights_unique: int
    failed_accounts: tuple[MarketingMetaAccountFailure, ...]
    replaced_canonical_run_id: int | None


def _session_or_default(session: Any | None):
    return session if session is not None else db.session


def _normalize_accounts(
    accounts: Iterable[MarketingMetaAccount],
) -> tuple[MarketingMetaAccount, ...]:
    normalized: list[MarketingMetaAccount] = []
    for account in accounts:
        if not isinstance(account, MarketingMetaAccount):
            raise TypeError(
                "accounts debe contener MarketingMetaAccount."
            )
        token = str(account.access_token or "").strip()
        if not token:
            raise ValueError("Una cuenta Meta no tiene access token.")
        normalized.append(
            MarketingMetaAccount(
                account_id=normalize_meta_account_id(
                    account.account_id
                ),
                access_token=token,
            )
        )

    if not normalized:
        raise ValueError("Debe indicarse al menos una cuenta Meta.")
    account_ids = [account.account_id for account in normalized]
    if len(account_ids) != len(set(account_ids)):
        raise ValueError("Las cuentas Meta no pueden repetirse.")
    return tuple(normalized)


def _terminal_status(
    *,
    accounts_requested: int,
    accounts_completed: int,
    accounts_failed: int,
) -> str:
    if accounts_completed + accounts_failed != accounts_requested:
        raise MarketingMetaRunSyncError(
            "La contabilidad de cuentas Meta es incompleta."
        )
    if accounts_failed == 0:
        return SYNC_STATUS_COMPLETED
    if accounts_completed > 0:
        return SYNC_STATUS_PARTIAL
    return SYNC_STATUS_FAILED


def sync_meta_full_run(
    *,
    period_key: str,
    date_from: date,
    date_to: date,
    accounts: Iterable[MarketingMetaAccount],
    client: Any | None = None,
    page_limit: int = 500,
    max_pages_per_account: int = 10000,
    make_canonical_on_completed: bool = True,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    session: Any | None = None,
) -> MarketingMetaRunSyncResult:
    account_values = _normalize_accounts(accounts)
    if date_from > date_to:
        raise ValueError(
            "date_from no puede ser posterior a date_to."
        )
    if page_limit <= 0 or page_limit > 500:
        raise ValueError("page_limit debe estar entre 1 y 500.")
    if max_pages_per_account <= 0:
        raise ValueError("max_pages_per_account debe ser positivo.")
    if not isinstance(make_canonical_on_completed, bool):
        raise TypeError("make_canonical_on_completed debe ser bool.")

    session_value = _session_or_default(session)
    client_value = client if client is not None else MetaInsightsClient()
    run = create_meta_sync_run_running(
        period_key=period_key,
        date_from=date_from,
        date_to=date_to,
        accounts_requested=len(account_values),
        started_at=started_at,
        session=session_value,
    )
    if run.id is None:
        raise MarketingMetaRunSyncError(
            "El sync run Meta fue creado sin id."
        )
    sync_run_id = int(run.id)

    accounts_completed = 0
    accounts_failed = 0
    pages_received = 0
    insights_received = 0
    insights_unique = 0
    failures: list[MarketingMetaAccountFailure] = []

    try:
        for account in account_values:
            after = None
            page_number = 1
            try:
                while True:
                    if page_number > max_pages_per_account:
                        raise MarketingMetaRunSyncError(
                            "Meta excedió max_pages_per_account."
                        )

                    raw_response = client_value.fetch_insights_page(
                        account_id=account.account_id,
                        access_token=account.access_token,
                        date_from=date_from,
                        date_to=date_to,
                        after=after,
                        limit=page_limit,
                    )
                    raw_page = persist_meta_raw_page_pre_parse(
                        sync_run_id=sync_run_id,
                        account_id=account.account_id,
                        page_number=page_number,
                        raw_response=raw_response,
                        session=session_value,
                    )
                    pages_received += 1
                    page = parse_meta_raw_page(raw_response)
                    apply_meta_raw_page_parse_metadata(
                        raw_page_id=int(raw_page.id),
                        page=page,
                        session=session_value,
                    )
                    stored = persist_meta_structured_page(
                        sync_run_id=sync_run_id,
                        raw_page_id=int(raw_page.id),
                        insights=page.insights,
                        session=session_value,
                    )
                    insights_received += stored.insights_received
                    insights_unique += stored.insights_created

                    if not page.has_more:
                        break
                    after = page.next_cursor
                    page_number += 1

            except (MetaInsightsClientError, MarketingMetaParseError) as exc:
                session_value.rollback()
                accounts_failed += 1
                failures.append(
                    MarketingMetaAccountFailure(
                        account_id=account.account_id,
                        error_type=exc.__class__.__name__,
                    )
                )
                logger.warning(
                    "Meta account failed run=%s account=%s error=%s",
                    sync_run_id,
                    account.account_id,
                    exc.__class__.__name__,
                )
                continue

            accounts_completed += 1

        status = _terminal_status(
            accounts_requested=len(account_values),
            accounts_completed=accounts_completed,
            accounts_failed=accounts_failed,
        )
        counters = MarketingMetaRunCounters(
            accounts_completed=accounts_completed,
            accounts_failed=accounts_failed,
            pages_received=pages_received,
            insights_received=insights_received,
            insights_unique=insights_unique,
        )
        finalized = finalize_meta_sync_run(
            sync_run_id=sync_run_id,
            status=status,
            counters=counters,
            make_canonical=(
                status == SYNC_STATUS_COMPLETED
                and make_canonical_on_completed
            ),
            finished_at=finished_at,
            session=session_value,
        )
    except Exception:
        session_value.rollback()
        try:
            abort_failed = len(account_values) - accounts_completed
            finalize_meta_sync_run(
                sync_run_id=sync_run_id,
                status=SYNC_STATUS_FAILED,
                counters=MarketingMetaRunCounters(
                    accounts_completed=accounts_completed,
                    accounts_failed=abort_failed,
                    pages_received=pages_received,
                    insights_received=insights_received,
                    insights_unique=insights_unique,
                ),
                make_canonical=False,
                finished_at=finished_at,
                session=session_value,
            )
        except Exception:
            session_value.rollback()
            logger.exception(
                "No fue posible cerrar el run Meta abortado=%s",
                sync_run_id,
            )
        raise

    return MarketingMetaRunSyncResult(
        sync_run_id=sync_run_id,
        period_key=finalized.period_key,
        status=finalized.status,
        is_canonical=finalized.is_canonical,
        accounts_requested=len(account_values),
        accounts_completed=accounts_completed,
        accounts_failed=accounts_failed,
        pages_received=pages_received,
        insights_received=insights_received,
        insights_unique=insights_unique,
        failed_accounts=tuple(failures),
        replaced_canonical_run_id=(
            finalized.replaced_canonical_run_id
        ),
    )
