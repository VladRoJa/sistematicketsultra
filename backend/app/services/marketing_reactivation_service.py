"""Operación de cartera y campañas para Reactivación de Marketing.

La evidencia CRM y el estado operativo siguen viniendo de los resolvers
existentes. Esta capa añade una elegibilidad separada, auditable y común
para preview, creación y revalidación previa a exportar.
"""

from __future__ import annotations

import base64
import binascii
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
from io import BytesIO
import json
from typing import Any
import unicodedata

from openpyxl import Workbook
from sqlalchemy import false, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import (
    MarketingIventasSyncRunORM,
    MarketingReactivationCampaignORM,
    MarketingReactivationCampaignRecipientORM,
    MarketingReactivationTariffORM,
)
from app.models.warehouse import SociosVencidosCarteraORM
from app.services.marketing_iventas_service import normalize_iventas_phone
from app.services.marketing_reactivation_candidate_query import (
    DEFAULT_DIRECTION,
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    DEFAULT_SORT,
    ReactivationCandidateCursor,
    ReactivationCandidateQuery,
    apply_candidate_cursor,
    build_latest_operational_episode_query,
    build_phone_variant_filter,
    candidate_sort_value,
    normalize_candidate_query,
)
from app.warehouse.services.socios_vencidos_current_status_resolver import (
    STATUS_NOT_FOUND,
    normalize_socios_vencidos_branch_key,
    resolve_socios_vencidos_rows_with_context,
)
from app.warehouse.services.socios_vencidos_reactivation_candidate_resolver import (
    SociosVencidosReactivationCandidateResolverError,
    count_socios_vencidos_not_found_phones,
    prepare_socios_vencidos_reactivation_resolution_context,
    resolve_socios_vencidos_reactivation_candidate_batch,
)


CAMPAIGN_STATUS_DRAFT = "DRAFT"
CAMPAIGN_STATUS_EXPORTED = "EXPORTED"
CAMPAIGN_STATUS_SENT = "SENT"
CAMPAIGN_STATUS_CANCELLED = "CANCELLED"

ELIGIBILITY_ELIGIBLE = "ELIGIBLE"
ELIGIBILITY_EXCLUDED_ACTIVE = "EXCLUDED_ACTIVE"
ELIGIBILITY_EXCLUDED_INVALID_PHONE = "EXCLUDED_INVALID_PHONE"
ELIGIBILITY_EXCLUDED_TARIFF = "EXCLUDED_TARIFF"
ELIGIBILITY_EXCLUDED_RECENT_CAMPAIGN = "EXCLUDED_RECENT_CAMPAIGN"
ELIGIBILITY_REVIEW = "REVIEW"

REASON_REVIEW_IDENTITY = "REVIEW_IDENTITY"
REASON_REVIEW_DUPLICATE_PHONE = "REVIEW_DUPLICATE_PHONE"
REASON_REVIEW_TARIFF = "REVIEW_TARIFF"
REASON_INVALID_PHONE = "INVALID_PHONE"
REASON_RECENT_SUITE_CAMPAIGN = "RECENT_SUITE_CAMPAIGN"
REASON_TARIFF_EXCLUDED = "TARIFF_EXCLUDED"
REASON_TARIFF_DOMICILIATED_FLOW = "TARIFF_DOMICILIATED_FLOW"

TARIFF_GROUP_REACTIVATE = "REACTIVATE"
TARIFF_GROUP_DOMICILIATED_FLOW = "DOMICILIATED_FLOW"
TARIFF_GROUP_EXCLUDE = "EXCLUDE"
TARIFF_GROUP_REVIEW = "REVIEW"

OPERATIONAL_NO_CONTACT_IN_PERIOD = "NO_CONTACT_IN_PERIOD"
OPERATIONAL_NO_OUTBOUND_MESSAGE = "NO_OUTBOUND_MESSAGE"
OPERATIONAL_CONTACTED_BEFORE_EXPIRATION = "CONTACTED_BEFORE_EXPIRATION"
OPERATIONAL_CONTACTED_AFTER_EXPIRATION = "CONTACTED_AFTER_EXPIRATION"
OPERATIONAL_REVIEW_IDENTITY = "REVIEW_IDENTITY"
OPERATIONAL_ACTIVE = "ACTIVE"

FILTER_WORK_PENDING = "WORK_PENDING"
FILTER_ALL = "ALL"

_OPERATIONAL_FILTERS = frozenset(
    {
        FILTER_WORK_PENDING,
        FILTER_ALL,
        OPERATIONAL_NO_CONTACT_IN_PERIOD,
        OPERATIONAL_NO_OUTBOUND_MESSAGE,
        OPERATIONAL_CONTACTED_BEFORE_EXPIRATION,
        OPERATIONAL_CONTACTED_AFTER_EXPIRATION,
        OPERATIONAL_REVIEW_IDENTITY,
        OPERATIONAL_ACTIVE,
    }
)
_IDENTITY_REASONS = frozenset(
    {
        "ACTIVE_REVIEW",
        "AMBIGUOUS",
        "IDENTIFIER_CONFLICT",
        "AMBIGUOUS_IVENTAS_IDENTITY",
    }
)
_ALLOWED_CAMPAIGN_FILTERS = frozenset(
    {
        "iventas_period_key",
        "sucursal",
        "operational_status",
        "search",
        "tarifa",
        "tariff_group",
        "campaign_cooldown_days",
    }
)
_TARIFF_GROUPS = frozenset(
    {
        TARIFF_GROUP_REACTIVATE,
        TARIFF_GROUP_DOMICILIATED_FLOW,
        TARIFF_GROUP_EXCLUDE,
        TARIFF_GROUP_REVIEW,
    }
)
_CANDIDATE_BATCH_SIZE = 250


class MarketingReactivationValidationError(ValueError):
    pass


class MarketingReactivationNotFoundError(LookupError):
    pass


class MarketingReactivationConflictError(RuntimeError):
    pass


class MarketingReactivationInvalidTransitionError(RuntimeError):
    pass


def _session_or_default(session: Any | None):
    return session if session is not None else db.session


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def list_marketing_reactivation_sources(
    *,
    allowed_sucursal_keys: tuple[str, ...] | None = None,
    session: Any | None = None,
) -> dict[str, object]:
    """Lista cobertura de cartera y runs iVentas canónicos disponibles."""

    active_session = _session_or_default(session)
    coverage_query = active_session.query(
        func.min(SociosVencidosCarteraORM.fecha_vencimiento_date),
        func.max(SociosVencidosCarteraORM.fecha_vencimiento_date),
        func.count(SociosVencidosCarteraORM.id),
    )
    if allowed_sucursal_keys is not None:
        coverage_query = coverage_query.filter(
            SociosVencidosCarteraORM.sucursal_key.in_(allowed_sucursal_keys)
            if allowed_sucursal_keys
            else false()
        )
    coverage = coverage_query.one()
    iventas_runs = (
        active_session.query(MarketingIventasSyncRunORM)
        .filter(
            MarketingIventasSyncRunORM.status == "COMPLETED",
            MarketingIventasSyncRunORM.is_canonical.is_(True),
        )
        .order_by(
            MarketingIventasSyncRunORM.date_to.desc(),
            MarketingIventasSyncRunORM.id.desc(),
        )
        .all()
    )
    return {
        "vencidos_coverage": {
            "min_date": (
                _serialize_date(coverage[0]) if coverage[0] is not None else None
            ),
            "max_date": (
                _serialize_date(coverage[1]) if coverage[1] is not None else None
            ),
            "total_rows": int(coverage[2] or 0),
        },
        "iventas_periods": [
            {
                "period_key": str(run.period_key),
                "sync_run_id": int(run.id),
                "date_from": _serialize_date(run.date_from),
                "date_to": _serialize_date(run.date_to),
                "contacts_unique": int(run.contacts_unique),
            }
            for run in iventas_runs
        ],
        "branches": _list_operational_branches(
            date_from=coverage[0],
            date_to=coverage[1],
            allowed_sucursal_keys=allowed_sucursal_keys,
            session=active_session,
        ),
    }


def _list_operational_branches(
    *,
    date_from: date | None,
    date_to: date | None,
    allowed_sucursal_keys: tuple[str, ...] | None,
    session: Any,
) -> list[dict[str, str]]:
    if date_from is None or date_to is None:
        return []
    query = build_latest_operational_episode_query(
        session=session,
        date_from=date_from,
        date_to=date_to,
        allowed_sucursal_keys=allowed_sucursal_keys,
    )
    rows = (
        query.order_by(None)
        .with_entities(
            SociosVencidosCarteraORM.sucursal_key,
            func.min(SociosVencidosCarteraORM.sucursal_raw),
        )
        .group_by(SociosVencidosCarteraORM.sucursal_key)
        .order_by(
            func.min(SociosVencidosCarteraORM.sucursal_raw).asc().nullslast(),
            SociosVencidosCarteraORM.sucursal_key.asc(),
        )
        .all()
    )
    return [
        {"key": str(branch_key), "label": str(branch_label)}
        for branch_key, branch_label in rows
        if branch_key is not None and branch_label is not None
    ]


def list_marketing_reactivation_tariffs(
    *,
    date_from: date | str,
    date_to: date | str,
    allowed_sucursal_keys: tuple[str, ...] | None = None,
    session: Any | None = None,
) -> dict[str, object]:
    normalized_from, normalized_to = _validate_date_range(date_from, date_to)
    active_session = _session_or_default(session)
    operational_query = build_latest_operational_episode_query(
        session=active_session,
        date_from=normalized_from,
        date_to=normalized_to,
        allowed_sucursal_keys=allowed_sucursal_keys,
    )
    rows = (
        operational_query.order_by(None)
        .with_entities(
            SociosVencidosCarteraORM.tarifa,
            func.count(SociosVencidosCarteraORM.id),
        )
        .group_by(SociosVencidosCarteraORM.tarifa)
        .order_by(SociosVencidosCarteraORM.tarifa.asc().nullslast())
        .all()
    )
    catalog = _read_active_tariff_catalog(
        tariff_values=(tarifa for tarifa, _ in rows),
        session=active_session,
    )
    return {
        "date_from": normalized_from.isoformat(),
        "date_to": normalized_to.isoformat(),
        "rows": [
            {
                "tarifa": tarifa,
                "count": int(count_value),
                **_serialize_tariff_classification(
                    catalog.get(normalize_reactivation_tariff_key(tarifa))
                ),
            }
            for tarifa, count_value in rows
        ],
    }


def build_marketing_reactivation_candidates(
    *,
    date_from: date | str,
    date_to: date | str,
    iventas_period_key: str,
    page: Any = DEFAULT_PAGE,
    page_size: Any = DEFAULT_PAGE_SIZE,
    sucursal: Any = None,
    tarifa: Any = None,
    tariff_group: Any = None,
    operational_status: Any = FILTER_ALL,
    search: Any = None,
    sort: Any = DEFAULT_SORT,
    direction: Any = DEFAULT_DIRECTION,
    cursor: Any = None,
    allowed_sucursal_keys: tuple[str, ...] | None = None,
    session: Any | None = None,
) -> dict[str, object]:
    """Devuelve una página sin resolver el segmento operativo completo."""

    query = _normalize_reactivation_candidate_request(
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
        sucursal=sucursal,
        tarifa=tarifa,
        tariff_group=tariff_group,
        operational_status=operational_status,
        search=search,
        sort=sort,
        direction=direction,
        cursor=cursor,
    )
    _validate_requested_sucursal_scope(
        sucursal=query.sucursal,
        allowed_sucursal_keys=allowed_sucursal_keys,
    )
    return _build_marketing_reactivation_candidate_page(
        query=query,
        iventas_period_key=iventas_period_key,
        session=_session_or_default(session),
        allowed_sucursal_keys=allowed_sucursal_keys,
    )


def build_marketing_reactivation_candidate_summary(
    *,
    date_from: date | str,
    date_to: date | str,
    iventas_period_key: str,
    sucursal: Any = None,
    tarifa: Any = None,
    tariff_group: Any = None,
    operational_status: Any = FILTER_ALL,
    search: Any = None,
    allowed_sucursal_keys: tuple[str, ...] | None = None,
    session: Any | None = None,
) -> dict[str, object]:
    """Calcula agregados completos, independientemente de página y orden."""

    query = _normalize_reactivation_candidate_request(
        date_from=date_from,
        date_to=date_to,
        page=DEFAULT_PAGE,
        page_size=DEFAULT_PAGE_SIZE,
        sucursal=sucursal,
        tarifa=tarifa,
        tariff_group=tariff_group,
        operational_status=operational_status,
        search=search,
        sort=DEFAULT_SORT,
        direction=DEFAULT_DIRECTION,
    )
    _validate_requested_sucursal_scope(
        sucursal=query.sucursal,
        allowed_sucursal_keys=allowed_sucursal_keys,
    )
    return _build_marketing_reactivation_candidate_summary(
        query=query,
        iventas_period_key=iventas_period_key,
        session=_session_or_default(session),
        allowed_sucursal_keys=allowed_sucursal_keys,
    )


def _normalize_reactivation_candidate_request(
    **values: Any,
) -> ReactivationCandidateQuery:
    try:
        query = normalize_candidate_query(**values)
    except ValueError as exc:
        raise MarketingReactivationValidationError(str(exc)) from exc
    requested_status = query.operational_status or FILTER_ALL
    if requested_status not in _OPERATIONAL_FILTERS:
        raise MarketingReactivationValidationError(
            "operational_status no es válido."
        )
    if query.tariff_group and query.tariff_group not in _TARIFF_GROUPS:
        raise MarketingReactivationValidationError(
            "tariff_group no es válido."
        )
    return query


def _build_marketing_reactivation_candidate_page(
    *,
    query: ReactivationCandidateQuery,
    iventas_period_key: str,
    session: Any,
    allowed_sucursal_keys: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    base_query = _build_candidate_base_query(
        query=query,
        session=session,
        allowed_sucursal_keys=allowed_sucursal_keys,
    )
    context = prepare_socios_vencidos_reactivation_resolution_context(
        minimum_cutoff_date=query.date_to,
        iventas_period_key=iventas_period_key,
        activos_snapshot_id=None,
        session=session,
    )
    tariff_catalog = _read_all_active_tariff_catalog(session=session)
    requested_status = query.operational_status or FILTER_ALL
    if requested_status == FILTER_ALL:
        if query.cursor is not None:
            raise MarketingReactivationValidationError(
                "cursor sólo aplica a filtros de operational_status derivados."
            )
        total_rows = int(base_query.order_by(None).count())
        page_rows = (
            base_query
            .offset((query.page - 1) * query.page_size)
            .limit(query.page_size)
            .all()
        )
        serialized_rows = _resolve_interactive_candidate_batch(
            vencidos_rows=page_rows,
            query=query,
            context=context,
            tariff_catalog=tariff_catalog,
            session=session,
            allowed_sucursal_keys=allowed_sucursal_keys,
        )
        return _candidate_page_response(
            query=query,
            context=context,
            rows=serialized_rows,
            total=total_rows,
            total_pages=(total_rows + query.page_size - 1) // query.page_size,
            has_next=query.page * query.page_size < total_rows,
            has_prev=query.page > 1,
            next_cursor=None,
        )

    if query.page > 1 and query.cursor is None:
        raise MarketingReactivationValidationError(
            "cursor es obligatorio después de la primera página para "
            "operational_status derivados."
        )
    segment_key = _candidate_cursor_segment_key(
        query=query,
        iventas_period_key=iventas_period_key,
        allowed_sucursal_keys=allowed_sucursal_keys,
    )
    scan_cursor = (
        _decode_candidate_cursor(
            query.cursor,
            query=query,
            expected_segment_key=segment_key,
        )
        if query.cursor is not None
        else None
    )
    selected_rows: list[dict[str, Any]] = []
    selected_source_row: Any | None = None
    exhausted = False
    batch_size = min(_CANDIDATE_BATCH_SIZE, max(DEFAULT_PAGE_SIZE, query.page_size))
    while len(selected_rows) < query.page_size:
        batch_query = base_query
        if scan_cursor is not None:
            batch_query = apply_candidate_cursor(
                batch_query,
                cursor=scan_cursor,
                sort=query.sort,
                direction=query.direction,
            )
        batch = list(batch_query.limit(batch_size).all())
        if not batch:
            exhausted = True
            break
        serialized_batch = _resolve_interactive_candidate_batch(
            vencidos_rows=batch,
            query=query,
            context=context,
            tariff_catalog=tariff_catalog,
            session=session,
            allowed_sucursal_keys=allowed_sucursal_keys,
        )
        serialized_by_id = {
            int(row["vencido_row_id"]): row for row in serialized_batch
        }
        for source_row in batch:
            serialized = serialized_by_id[int(source_row.id)]
            if _matches_operational_status(
                str(serialized["operational_status"]),
                requested_status,
            ):
                selected_rows.append(serialized)
                selected_source_row = source_row
                if len(selected_rows) == query.page_size:
                    break
        if len(selected_rows) == query.page_size:
            break
        last_row = batch[-1]
        scan_cursor = ReactivationCandidateCursor(
            sort_value=candidate_sort_value(last_row, query.sort),
            row_id=int(last_row.id),
        )
        if len(batch) < batch_size:
            exhausted = True
            break

    next_cursor = (
        _encode_candidate_cursor(
            selected_source_row,
            query=query,
            segment_key=segment_key,
        )
        if selected_source_row is not None
        and len(selected_rows) == query.page_size
        and not exhausted
        else None
    )
    return _candidate_page_response(
        query=query,
        context=context,
        rows=selected_rows,
        total=None,
        total_pages=None,
        has_next=next_cursor is not None,
        has_prev=query.cursor is not None,
        next_cursor=next_cursor,
    )


def _build_marketing_reactivation_candidate_summary(
    *,
    query: ReactivationCandidateQuery,
    iventas_period_key: str,
    session: Any,
    allowed_sucursal_keys: tuple[str, ...] | None,
) -> dict[str, Any]:
    base_query = _build_candidate_base_query(
        query=query,
        session=session,
        allowed_sucursal_keys=allowed_sucursal_keys,
    ).order_by(None)
    context = prepare_socios_vencidos_reactivation_resolution_context(
        minimum_cutoff_date=query.date_to,
        iventas_period_key=iventas_period_key,
        activos_snapshot_id=None,
        session=session,
    )
    phone_counts = _count_complete_segment_not_found_phones(
        base_query=base_query,
        context=context,
    )
    tariff_catalog = _read_all_active_tariff_catalog(session=session)
    status_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    total_rows = 0
    for serialized in _iter_complete_segment_candidates(
        base_query=base_query,
        context=context,
        phone_counts=phone_counts,
        tariff_catalog=tariff_catalog,
        session=session,
    ):
        if not _matches_operational_status(
            str(serialized["operational_status"]),
            query.operational_status or FILTER_ALL,
        ):
            continue
        total_rows += 1
        status_counts[str(serialized["status"])] += 1
        reason_counts[str(serialized["reason"])] += 1
    return {
        "sources": _candidate_sources(query=query, context=context),
        "summary": {
            "total_rows": total_rows,
            "status_counts": dict(status_counts),
            "reason_counts": dict(reason_counts),
        },
    }


def _build_marketing_reactivation_campaign_segment(
    *,
    query: ReactivationCandidateQuery,
    iventas_period_key: str,
    session: Any,
    allowed_sucursal_keys: tuple[str, ...] | None,
) -> dict[str, Any]:
    base_query = _build_candidate_base_query(
        query=query,
        session=session,
        allowed_sucursal_keys=allowed_sucursal_keys,
    )
    context = prepare_socios_vencidos_reactivation_resolution_context(
        minimum_cutoff_date=query.date_to,
        iventas_period_key=iventas_period_key,
        activos_snapshot_id=None,
        session=session,
    )
    phone_counts = _count_complete_segment_not_found_phones(
        base_query=base_query.order_by(None),
        context=context,
    )
    tariff_catalog = _read_all_active_tariff_catalog(session=session)
    rows = [
        serialized
        for serialized in _iter_complete_segment_candidates(
            base_query=base_query,
            context=context,
            phone_counts=phone_counts,
            tariff_catalog=tariff_catalog,
            session=session,
        )
        if _matches_operational_status(
            str(serialized["operational_status"]),
            query.operational_status or FILTER_ALL,
        )
    ]
    return {
        "sources": _candidate_sources(query=query, context=context),
        "rows": rows,
    }


def _build_candidate_base_query(
    *,
    query: ReactivationCandidateQuery,
    session: Any,
    allowed_sucursal_keys: tuple[str, ...] | None,
):
    return build_latest_operational_episode_query(
        session=session,
        date_from=query.date_from,
        date_to=query.date_to,
        sucursal=query.sucursal,
        tarifa=query.tarifa,
        tariff_group=query.tariff_group,
        search=query.search,
        sort=query.sort,
        direction=query.direction,
        allowed_sucursal_keys=allowed_sucursal_keys,
    )


def _count_complete_segment_not_found_phones(
    *,
    base_query: Any,
    context: Any,
) -> Counter[str]:
    phone_counts: Counter[str] = Counter()
    for batch in _iter_query_batches(base_query, _CANDIDATE_BATCH_SIZE):
        phone_counts.update(
            count_socios_vencidos_not_found_phones(
                vencidos_rows=batch,
                context=context,
            )
        )
    return phone_counts


def _iter_complete_segment_candidates(
    *,
    base_query: Any,
    context: Any,
    phone_counts: Counter[str],
    tariff_catalog: dict[str, MarketingReactivationTariffORM],
    session: Any,
):
    for batch in _iter_query_batches(base_query, _CANDIDATE_BATCH_SIZE):
        candidates = resolve_socios_vencidos_reactivation_candidate_batch(
            vencidos_rows=batch,
            context=context,
            phone_counts=phone_counts,
            session=session,
        )
        yield from _serialize_resolved_batch(
            vencidos_rows=batch,
            candidates=candidates,
            tariff_catalog=tariff_catalog,
        )


def _resolve_interactive_candidate_batch(
    *,
    vencidos_rows: list[Any],
    query: ReactivationCandidateQuery,
    context: Any,
    tariff_catalog: dict[str, MarketingReactivationTariffORM],
    session: Any,
    allowed_sucursal_keys: tuple[str, ...] | None,
) -> list[dict[str, Any]]:
    if not vencidos_rows:
        return []
    current_rows = resolve_socios_vencidos_rows_with_context(
        vencidos_rows=vencidos_rows,
        context=context.current_status,
    )
    source_by_id = {int(row.id): row for row in vencidos_rows}
    phone_counts = Counter(
        phone
        for phone in (
            normalize_iventas_phone(
                source_by_id[int(current_row.vencido_row_id)].telefono_raw
            ).phone_mx10
            for current_row in current_rows
            if current_row.status == STATUS_NOT_FOUND
        )
        if phone is not None
    )
    target_phones = set(phone_counts)
    if target_phones:
        peer_query = _build_candidate_base_query(
            query=query,
            session=session,
            allowed_sucursal_keys=allowed_sucursal_keys,
        ).filter(
            build_phone_variant_filter(target_phones),
            SociosVencidosCarteraORM.id.notin_(tuple(source_by_id)),
        ).order_by(None)
        for peer_batch in _iter_query_batches(peer_query, _CANDIDATE_BATCH_SIZE):
            phone_counts.update(
                count_socios_vencidos_not_found_phones(
                    vencidos_rows=peer_batch,
                    context=context,
                )
            )
    candidates = resolve_socios_vencidos_reactivation_candidate_batch(
        vencidos_rows=vencidos_rows,
        context=context,
        phone_counts=phone_counts,
        current_rows=current_rows,
        session=session,
    )
    return list(_serialize_resolved_batch(
        vencidos_rows=vencidos_rows,
        candidates=candidates,
        tariff_catalog=tariff_catalog,
    ))


def _serialize_resolved_batch(
    *,
    vencidos_rows: list[Any],
    candidates: Any,
    tariff_catalog: dict[str, MarketingReactivationTariffORM],
):
    candidate_by_id = {
        int(candidate.vencido_row_id): candidate for candidate in candidates
    }
    for vencido_row in vencidos_rows:
        candidate = candidate_by_id.get(int(vencido_row.id))
        if candidate is None:
            raise SociosVencidosReactivationCandidateResolverError(
                "El lote resuelto no contiene todos los episodios."
            )
        serialized = _serialize_candidate(
            candidate=candidate,
            vencido_row=vencido_row,
            tariff_catalog=tariff_catalog,
        )
        serialized["operational_status"] = _operational_status(serialized)
        yield serialized


def _candidate_page_response(
    *,
    query: ReactivationCandidateQuery,
    context: Any,
    rows: list[dict[str, Any]],
    total: int | None,
    total_pages: int | None,
    has_next: bool,
    has_prev: bool,
    next_cursor: str | None,
) -> dict[str, Any]:
    return {
        "sources": _candidate_sources(query=query, context=context),
        "pagination": {
            "page": query.page,
            "page_size": query.page_size,
            "total": total,
            "total_pages": total_pages,
            "has_next": has_next,
            "has_prev": has_prev,
            "next_cursor": next_cursor,
        },
        "rows": rows,
    }


def _candidate_sources(*, query: ReactivationCandidateQuery, context: Any):
    return {
        "date_from": query.date_from.isoformat(),
        "date_to": query.date_to.isoformat(),
        "activos_snapshot_id": int(context.current_status.activos_snapshot_id),
        "iventas_sync_run_id": int(context.iventas_sync_run_id),
        "iventas_period_key": str(context.iventas_period_key),
    }


def _candidate_cursor_segment_key(
    *,
    query: ReactivationCandidateQuery,
    iventas_period_key: str,
    allowed_sucursal_keys: tuple[str, ...] | None,
) -> str:
    document = {
        "date_from": query.date_from.isoformat(),
        "date_to": query.date_to.isoformat(),
        "iventas_period_key": str(iventas_period_key),
        "sucursal": query.sucursal,
        "tarifa": query.tarifa,
        "tariff_group": query.tariff_group,
        "operational_status": query.operational_status or FILTER_ALL,
        "search": query.search,
        "sort": query.sort,
        "direction": query.direction,
        "allowed_sucursal_keys": allowed_sucursal_keys,
    }
    encoded = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _encode_candidate_cursor(
    row: Any,
    *,
    query: ReactivationCandidateQuery,
    segment_key: str,
) -> str:
    value = candidate_sort_value(row, query.sort)
    if isinstance(value, (date, datetime, Decimal)):
        value = str(value.isoformat() if hasattr(value, "isoformat") else value)
    payload = {
        "v": 1,
        "sort": query.sort,
        "direction": query.direction,
        "value": value,
        "id": int(row.id),
        "segment": segment_key,
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_candidate_cursor(
    raw_cursor: str,
    *,
    query: ReactivationCandidateQuery,
    expected_segment_key: str,
) -> ReactivationCandidateCursor:
    try:
        padded = raw_cursor + "=" * (-len(raw_cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        if (
            not isinstance(payload, dict)
            or payload.get("v") != 1
            or payload.get("sort") != query.sort
            or payload.get("direction") != query.direction
            or payload.get("segment") != expected_segment_key
            or isinstance(payload.get("id"), bool)
            or int(payload.get("id")) <= 0
        ):
            raise ValueError
        value = payload.get("value")
        if value is not None and query.sort == "fecha_vencimiento":
            value = date.fromisoformat(str(value))
        elif value is not None and query.sort == "fecha_ultimo_pago":
            value = datetime.fromisoformat(str(value))
        elif value is not None and not isinstance(value, str):
            raise ValueError
        return ReactivationCandidateCursor(
            sort_value=value,
            row_id=int(payload["id"]),
        )
    except (
        binascii.Error,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
    ) as exc:
        raise MarketingReactivationValidationError(
            "cursor no es válido para el segmento y orden solicitados."
        ) from exc


def _validate_requested_sucursal_scope(
    *,
    sucursal: str | None,
    allowed_sucursal_keys: tuple[str, ...] | None,
) -> None:
    if sucursal is None or allowed_sucursal_keys is None:
        return
    requested_key = normalize_socios_vencidos_branch_key(sucursal)
    if requested_key not in set(allowed_sucursal_keys):
        raise MarketingReactivationValidationError(
            "filters.sucursal está fuera del alcance autorizado."
        )


def _iter_query_batches(query: Any, batch_size: int):
    batch: list[Any] = []
    for row in query.yield_per(batch_size):
        batch.append(row)
        if len(batch) == batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def _matches_operational_status(
    operational_status: str,
    requested_status: str,
) -> bool:
    if requested_status == FILTER_ALL:
        return True
    if requested_status == FILTER_WORK_PENDING:
        return operational_status not in {
            OPERATIONAL_ACTIVE,
            OPERATIONAL_CONTACTED_AFTER_EXPIRATION,
        }
    return operational_status == requested_status


def preview_marketing_reactivation_campaign(
    *,
    date_from: date | str,
    date_to: date | str,
    filters: Any,
    campaign_cooldown_days: int | None = None,
    allowed_sucursal_keys: tuple[str, ...] | None = None,
    session: Any | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    plan = _build_campaign_plan(
        date_from=date_from,
        date_to=date_to,
        filters=filters,
        campaign_cooldown_days=campaign_cooldown_days,
        allowed_sucursal_keys=allowed_sucursal_keys,
        session=_session_or_default(session),
        now=now,
    )
    return {
        "sources": plan["sources"],
        "filters": plan["filters"],
        "summary": plan["summary"],
    }


def create_marketing_reactivation_campaign(
    *,
    name: Any,
    date_from: date | str,
    date_to: date | str,
    filters: Any,
    notes: Any = None,
    created_by_user_id: int,
    campaign_cooldown_days: int | None = None,
    allowed_sucursal_keys: tuple[str, ...] | None = None,
    session: Any | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    normalized_name = _validate_required_text(name, "name", max_length=255)
    normalized_notes = _validate_optional_text(notes, "notes", max_length=5000)
    active_session = _session_or_default(session)
    now_value = _validate_now(now)
    plan = _build_campaign_plan(
        date_from=date_from,
        date_to=date_to,
        filters=filters,
        campaign_cooldown_days=campaign_cooldown_days,
        allowed_sucursal_keys=allowed_sucursal_keys,
        session=active_session,
        now=now_value,
    )
    eligible_rows = plan["eligible_rows"]
    if not eligible_rows:
        raise MarketingReactivationValidationError(
            "La selección no contiene destinatarios elegibles."
        )

    campaign = MarketingReactivationCampaignORM(
        name=normalized_name,
        status=CAMPAIGN_STATUS_DRAFT,
        date_from=date.fromisoformat(str(plan["sources"]["date_from"])),
        date_to=date.fromisoformat(str(plan["sources"]["date_to"])),
        created_by_user_id=int(created_by_user_id),
        created_at=now_value,
        updated_at=now_value,
        notes=normalized_notes,
        filters_json={
            "filters": plan["filters"],
            "sources": plan["sources"],
            "summary": plan["summary"],
            "scope": plan.get(
                "scope",
                _serialize_campaign_scope(allowed_sucursal_keys),
            ),
        },
        recipient_count=len(eligible_rows),
    )
    try:
        active_session.add(campaign)
        active_session.flush()
        for row in eligible_rows:
            active_session.add(
                MarketingReactivationCampaignRecipientORM(
                    campaign_id=int(campaign.id),
                    socios_vencidos_cartera_id=int(row["vencido_row_id"]),
                    phone_mx10=str(row["phone_mx10"]),
                    member_name=row["nombre"],
                    sucursal=str(row["sucursal"]),
                    fecha_vencimiento_date=date.fromisoformat(
                        str(row["fecha_vencimiento"])
                    ),
                    tarifa=row["tarifa"],
                    inclusion_status=ELIGIBILITY_ELIGIBLE,
                    exclusion_reason=None,
                    operational_status=str(row["operational_status"]),
                    operational_reason=str(row["reason"]),
                    created_at=now_value,
                )
            )
        active_session.commit()
    except IntegrityError as exc:
        active_session.rollback()
        raise MarketingReactivationConflictError(
            "Conflicto al guardar destinatarios únicos de la campaña."
        ) from exc
    except Exception:
        active_session.rollback()
        raise
    return serialize_marketing_reactivation_campaign(campaign)


def list_marketing_reactivation_campaigns(
    *,
    limit: int = 50,
    session: Any | None = None,
) -> dict[str, object]:
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 200:
        raise MarketingReactivationValidationError(
            "limit debe ser un entero entre 1 y 200."
        )
    active_session = _session_or_default(session)
    rows = (
        active_session.query(MarketingReactivationCampaignORM)
        .options(joinedload(MarketingReactivationCampaignORM.created_by_user))
        .order_by(
            MarketingReactivationCampaignORM.created_at.desc(),
            MarketingReactivationCampaignORM.id.desc(),
        )
        .limit(limit)
        .all()
    )
    return {
        "rows": [serialize_marketing_reactivation_campaign(row) for row in rows],
        "limit": limit,
    }


def get_marketing_reactivation_campaign(
    *,
    campaign_id: int,
    session: Any | None = None,
) -> dict[str, object]:
    campaign = _read_campaign(
        campaign_id=campaign_id,
        session=_session_or_default(session),
        include_recipients=True,
    )
    result = serialize_marketing_reactivation_campaign(campaign)
    result["recipients"] = [
        _serialize_campaign_recipient(row) for row in campaign.recipients
    ]
    return result


def export_marketing_reactivation_campaign(
    *,
    campaign_id: int,
    allowed_sucursal_keys: tuple[str, ...] | None = None,
    session: Any | None = None,
    now: datetime | None = None,
) -> tuple[bytes, str]:
    active_session = _session_or_default(session)
    campaign = _read_campaign(
        campaign_id=campaign_id,
        session=active_session,
        include_recipients=True,
        for_update=True,
    )
    if campaign.status not in {CAMPAIGN_STATUS_DRAFT, CAMPAIGN_STATUS_EXPORTED}:
        raise MarketingReactivationInvalidTransitionError(
            "Sólo una campaña DRAFT o EXPORTED puede exportarse."
        )
    stored_filters = dict((campaign.filters_json or {}).get("filters") or {})
    effective_scope = _resolve_frozen_campaign_scope_for_export(
        stored_scope=(campaign.filters_json or {}).get("scope"),
        current_allowed_sucursal_keys=allowed_sucursal_keys,
    )
    _validate_frozen_campaign_recipients_scope(
        recipients=campaign.recipients,
        effective_scope=effective_scope,
    )
    plan = _build_campaign_plan(
        date_from=campaign.date_from,
        date_to=campaign.date_to,
        filters=stored_filters,
        campaign_cooldown_days=stored_filters.get("campaign_cooldown_days"),
        allowed_sucursal_keys=effective_scope,
        session=active_session,
        now=now,
        exclude_campaign_id=int(campaign.id),
    )
    planned_keys = {
        (int(row["vencido_row_id"]), str(row["phone_mx10"]))
        for row in plan["eligible_rows"]
    }
    stored_keys = {
        (int(row.socios_vencidos_cartera_id), str(row.phone_mx10))
        for row in campaign.recipients
    }
    if planned_keys != stored_keys:
        raise MarketingReactivationConflictError(
            "La elegibilidad cambió desde la creación; prepara una campaña nueva."
        )

    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Destinatarios")
    sheet.append(["Nombre", "Teléfono", "Sucursal", "Fecha vencimiento", "Tarifa"])
    for row in campaign.recipients:
        sheet.append(
            [
                row.member_name or "",
                row.phone_mx10,
                row.sucursal,
                row.fecha_vencimiento_date.isoformat(),
                row.tarifa or "",
            ]
        )
    output = BytesIO()
    workbook.save(output)
    export_bytes = output.getvalue()
    now_value = _validate_now(now)
    if campaign.status == CAMPAIGN_STATUS_DRAFT:
        campaign.status = CAMPAIGN_STATUS_EXPORTED
        campaign.exported_at = now_value
        campaign.updated_at = now_value
    try:
        active_session.commit()
    except Exception:
        active_session.rollback()
        raise
    return export_bytes, f"reactivacion_campana_{int(campaign.id)}.xlsx"


def mark_marketing_reactivation_campaign_sent(
    *,
    campaign_id: int,
    session: Any | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    active_session = _session_or_default(session)
    campaign = _read_campaign(
        campaign_id=campaign_id,
        session=active_session,
        for_update=True,
    )
    if campaign.status != CAMPAIGN_STATUS_EXPORTED:
        raise MarketingReactivationInvalidTransitionError(
            "Sólo una campaña EXPORTED puede marcarse como SENT."
        )
    now_value = _validate_now(now)
    campaign.status = CAMPAIGN_STATUS_SENT
    campaign.sent_at = now_value
    campaign.updated_at = now_value
    try:
        active_session.commit()
    except Exception:
        active_session.rollback()
        raise
    return serialize_marketing_reactivation_campaign(campaign)


def serialize_marketing_reactivation_campaign(
    campaign: MarketingReactivationCampaignORM,
) -> dict[str, object]:
    user = getattr(campaign, "created_by_user", None)
    return {
        "id": int(campaign.id),
        "name": str(campaign.name),
        "status": str(campaign.status),
        "date_from": _serialize_date(campaign.date_from),
        "date_to": _serialize_date(campaign.date_to),
        "created_by_user_id": campaign.created_by_user_id,
        "created_by_username": getattr(user, "username", None),
        "created_at": _serialize_optional_aware_datetime(campaign.created_at),
        "updated_at": _serialize_optional_aware_datetime(campaign.updated_at),
        "exported_at": _serialize_optional_aware_datetime(campaign.exported_at),
        "sent_at": _serialize_optional_aware_datetime(campaign.sent_at),
        "notes": campaign.notes,
        "filters": dict((campaign.filters_json or {}).get("filters") or {}),
        "recipient_count": int(campaign.recipient_count),
    }


def _build_campaign_plan(
    *,
    date_from: date | str,
    date_to: date | str,
    filters: Any,
    campaign_cooldown_days: int | None,
    allowed_sucursal_keys: tuple[str, ...] | None,
    session: Any,
    now: datetime | None,
    exclude_campaign_id: int | None = None,
) -> dict[str, Any]:
    normalized_from, normalized_to = _validate_date_range(date_from, date_to)
    normalized_filters = _validate_campaign_filters(
        filters,
        campaign_cooldown_days=campaign_cooldown_days,
    )
    candidate_query = _normalize_reactivation_candidate_request(
        date_from=normalized_from,
        date_to=normalized_to,
        page=DEFAULT_PAGE,
        page_size=DEFAULT_PAGE_SIZE,
        sucursal=normalized_filters["sucursal"],
        tarifa=normalized_filters["tarifa"],
        tariff_group=normalized_filters["tariff_group"],
        operational_status=normalized_filters["operational_status"],
        search=normalized_filters["search"],
        sort=DEFAULT_SORT,
        direction=DEFAULT_DIRECTION,
    )
    _validate_requested_sucursal_scope(
        sucursal=normalized_filters["sucursal"],
        allowed_sucursal_keys=allowed_sucursal_keys,
    )
    effective_scope = _effective_campaign_scope(
        sucursal=normalized_filters["sucursal"],
        allowed_sucursal_keys=allowed_sucursal_keys,
    )
    candidates = _build_marketing_reactivation_campaign_segment(
        query=candidate_query,
        iventas_period_key=str(normalized_filters["iventas_period_key"]),
        session=session,
        allowed_sucursal_keys=allowed_sucursal_keys,
    )
    filtered_rows = [
        {
            **row,
            "operational_status": row.get("operational_status")
            or _operational_status(row),
        }
        for row in candidates["rows"]
    ]
    phone_by_row_id = {
        int(row["vencido_row_id"]): normalize_iventas_phone(
            row.get("telefono")
        ).phone_mx10
        for row in filtered_rows
    }
    phone_counts = Counter(
        phone for phone in phone_by_row_id.values() if phone is not None
    )
    last_sent_by_phone = _read_last_suite_campaign_sent_at(
        phone_mx10_values=set(phone_counts),
        session=session,
        exclude_campaign_id=exclude_campaign_id,
    )
    cooldown_days = normalized_filters.get("campaign_cooldown_days")
    now_value = _validate_now(now)
    eligibility_counts: Counter[str] = Counter()
    decision_rows: list[dict[str, Any]] = []
    for row in filtered_rows:
        phone_mx10 = phone_by_row_id[int(row["vencido_row_id"])]
        eligibility, reason = _resolve_campaign_eligibility(
            row=row,
            phone_mx10=phone_mx10,
            duplicate_phone=(
                phone_mx10 is not None and phone_counts[phone_mx10] > 1
            ),
            last_sent_at=(
                last_sent_by_phone.get(phone_mx10)
                if phone_mx10 is not None
                else None
            ),
            campaign_cooldown_days=cooldown_days,
            now=now_value,
        )
        eligibility_counts[eligibility] += 1
        decision_rows.append(
            {
                **row,
                "phone_mx10": phone_mx10,
                "campaign_eligibility": eligibility,
                "eligibility_reason": reason,
                "last_suite_campaign_sent_at": _serialize_optional_aware_datetime(
                    last_sent_by_phone.get(phone_mx10)
                    if phone_mx10 is not None
                    else None
                ),
            }
        )
    duplicate_count = sum(
        1
        for row in decision_rows
        if row["eligibility_reason"] == REASON_REVIEW_DUPLICATE_PHONE
    )
    review_identity_count = sum(
        1
        for row in decision_rows
        if row["campaign_eligibility"] == ELIGIBILITY_REVIEW
        and row["eligibility_reason"] == REASON_REVIEW_IDENTITY
    )
    domiciliated_flow_count = sum(
        1
        for row in decision_rows
        if row["eligibility_reason"] == REASON_TARIFF_DOMICILIATED_FLOW
    )
    review_tariff_count = sum(
        1
        for row in decision_rows
        if row["eligibility_reason"] == REASON_REVIEW_TARIFF
    )
    summary = {
        "total_candidates": len(decision_rows),
        "eligible": eligibility_counts[ELIGIBILITY_ELIGIBLE],
        "excluded_active": eligibility_counts[ELIGIBILITY_EXCLUDED_ACTIVE],
        "excluded_invalid_phone": eligibility_counts[
            ELIGIBILITY_EXCLUDED_INVALID_PHONE
        ],
        "review_identity": review_identity_count,
        "duplicate_phone": duplicate_count,
        "excluded_tariff": eligibility_counts[ELIGIBILITY_EXCLUDED_TARIFF],
        "domiciliated_flow": domiciliated_flow_count,
        "review_tariff": review_tariff_count,
        "excluded_recent_campaign": eligibility_counts[
            ELIGIBILITY_EXCLUDED_RECENT_CAMPAIGN
        ],
        "review": eligibility_counts[ELIGIBILITY_REVIEW],
    }
    return {
        "sources": candidates["sources"],
        "filters": normalized_filters,
        "scope": _serialize_campaign_scope(effective_scope),
        "summary": summary,
        "decision_rows": decision_rows,
        "eligible_rows": [
            row
            for row in decision_rows
            if row["campaign_eligibility"] == ELIGIBILITY_ELIGIBLE
        ],
    }


def _resolve_campaign_eligibility(
    *,
    row: dict[str, Any],
    phone_mx10: str | None,
    duplicate_phone: bool,
    last_sent_at: datetime | None,
    campaign_cooldown_days: int | None,
    now: datetime,
) -> tuple[str, str | None]:
    if row["status"] == "EXCLUDED_ACTIVE":
        return ELIGIBILITY_EXCLUDED_ACTIVE, "ACTIVE_CONFIRMED"
    if row["status"] == "REVIEW_ACTIVE_MATCH" or row["reason"] in _IDENTITY_REASONS:
        return ELIGIBILITY_REVIEW, REASON_REVIEW_IDENTITY
    tariff_group = row.get("tarifa_group")
    if tariff_group == TARIFF_GROUP_EXCLUDE:
        return ELIGIBILITY_EXCLUDED_TARIFF, REASON_TARIFF_EXCLUDED
    if tariff_group == TARIFF_GROUP_DOMICILIATED_FLOW:
        return ELIGIBILITY_EXCLUDED_TARIFF, REASON_TARIFF_DOMICILIATED_FLOW
    if tariff_group in {None, TARIFF_GROUP_REVIEW}:
        return ELIGIBILITY_REVIEW, REASON_REVIEW_TARIFF
    if tariff_group != TARIFF_GROUP_REACTIVATE:
        return ELIGIBILITY_REVIEW, REASON_REVIEW_TARIFF
    if phone_mx10 is None:
        return ELIGIBILITY_EXCLUDED_INVALID_PHONE, REASON_INVALID_PHONE
    if duplicate_phone:
        return ELIGIBILITY_REVIEW, REASON_REVIEW_DUPLICATE_PHONE
    if (
        campaign_cooldown_days is not None
        and last_sent_at is not None
        and last_sent_at >= now - timedelta(days=campaign_cooldown_days)
    ):
        return ELIGIBILITY_EXCLUDED_RECENT_CAMPAIGN, REASON_RECENT_SUITE_CAMPAIGN
    return ELIGIBILITY_ELIGIBLE, None


def _read_last_suite_campaign_sent_at(
    *,
    phone_mx10_values: set[str],
    session: Any,
    exclude_campaign_id: int | None = None,
) -> dict[str, datetime]:
    if not phone_mx10_values:
        return {}
    query = (
        session.query(
            MarketingReactivationCampaignRecipientORM.phone_mx10,
            func.max(MarketingReactivationCampaignORM.sent_at),
        )
        .join(
            MarketingReactivationCampaignORM,
            MarketingReactivationCampaignORM.id
            == MarketingReactivationCampaignRecipientORM.campaign_id,
        )
        .filter(
            MarketingReactivationCampaignORM.status == CAMPAIGN_STATUS_SENT,
            MarketingReactivationCampaignRecipientORM.phone_mx10.in_(
                tuple(sorted(phone_mx10_values))
            ),
        )
    )
    if exclude_campaign_id is not None:
        query = query.filter(
            MarketingReactivationCampaignORM.id != exclude_campaign_id
        )
    rows = query.group_by(
        MarketingReactivationCampaignRecipientORM.phone_mx10
    ).all()
    return {str(phone): sent_at for phone, sent_at in rows if sent_at is not None}


def _read_campaign(
    *,
    campaign_id: int,
    session: Any,
    include_recipients: bool = False,
    for_update: bool = False,
) -> MarketingReactivationCampaignORM:
    if not isinstance(campaign_id, int) or isinstance(campaign_id, bool) or campaign_id <= 0:
        raise MarketingReactivationValidationError(
            "campaign_id debe ser un entero positivo."
        )
    query = session.query(MarketingReactivationCampaignORM)
    if not for_update:
        query = query.options(
            joinedload(MarketingReactivationCampaignORM.created_by_user)
        )
    if include_recipients and not for_update:
        query = query.options(
            joinedload(MarketingReactivationCampaignORM.recipients)
        )
    if for_update:
        query = query.with_for_update()
    campaign = query.filter(
        MarketingReactivationCampaignORM.id == campaign_id
    ).one_or_none()
    if campaign is None:
        raise MarketingReactivationNotFoundError(
            f"No existe la campaña id={campaign_id}."
        )
    return campaign


def _validate_campaign_filters(
    filters: Any,
    *,
    campaign_cooldown_days: int | None,
) -> dict[str, Any]:
    if not isinstance(filters, dict):
        raise MarketingReactivationValidationError(
            "filters debe ser un objeto JSON."
        )
    unknown = sorted(set(filters) - _ALLOWED_CAMPAIGN_FILTERS)
    if unknown:
        raise MarketingReactivationValidationError(
            "Filtros no permitidos: " + ", ".join(unknown) + "."
        )
    iventas_period_key = _validate_required_text(
        filters.get("iventas_period_key"),
        "filters.iventas_period_key",
        max_length=64,
    )
    operational_status = str(
        filters.get("operational_status") or FILTER_WORK_PENDING
    ).strip()
    if operational_status not in _OPERATIONAL_FILTERS:
        raise MarketingReactivationValidationError(
            "filters.operational_status no es válido."
        )
    effective_cooldown = (
        campaign_cooldown_days
        if campaign_cooldown_days is not None
        else filters.get("campaign_cooldown_days")
    )
    if effective_cooldown is not None and (
        not isinstance(effective_cooldown, int)
        or isinstance(effective_cooldown, bool)
        or not 0 <= effective_cooldown <= 3650
    ):
        raise MarketingReactivationValidationError(
            "campaign_cooldown_days debe ser un entero entre 0 y 3650."
        )
    return {
        "iventas_period_key": iventas_period_key,
        "sucursal": _validate_optional_text(
            filters.get("sucursal"), "filters.sucursal", max_length=255
        ),
        "operational_status": operational_status,
        "search": _validate_optional_text(
            filters.get("search"), "filters.search", max_length=255
        ),
        "tarifa": _validate_optional_text(
            filters.get("tarifa"), "filters.tarifa", max_length=255
        ),
        "tariff_group": _validate_optional_tariff_group(
            filters.get("tariff_group"), "filters.tariff_group"
        ),
        "campaign_cooldown_days": effective_cooldown,
    }


def _serialize_campaign_scope(
    allowed_sucursal_keys: tuple[str, ...] | None,
) -> dict[str, Any]:
    return {
        "is_global": allowed_sucursal_keys is None,
        "allowed_sucursal_keys": (
            None
            if allowed_sucursal_keys is None
            else list(sorted(set(allowed_sucursal_keys)))
        ),
    }


def _effective_campaign_scope(
    *,
    sucursal: str | None,
    allowed_sucursal_keys: tuple[str, ...] | None,
) -> tuple[str, ...] | None:
    if sucursal is not None:
        requested_key = normalize_socios_vencidos_branch_key(sucursal)
        if requested_key is None:
            raise MarketingReactivationValidationError(
                "filters.sucursal no es válida."
            )
        return (requested_key,)
    return allowed_sucursal_keys


def _resolve_frozen_campaign_scope_for_export(
    *,
    stored_scope: Any,
    current_allowed_sucursal_keys: tuple[str, ...] | None,
) -> tuple[str, ...] | None:
    if not isinstance(stored_scope, dict):
        if current_allowed_sucursal_keys is not None:
            raise MarketingReactivationValidationError(
                "La campaña heredada no tiene scope auditable y no puede "
                "exportarse con alcance restringido."
            )
        return None
    frozen_is_global = stored_scope.get("is_global") is True
    frozen_values = stored_scope.get("allowed_sucursal_keys")
    if frozen_is_global:
        if frozen_values is not None:
            raise MarketingReactivationValidationError(
                "El scope congelado de la campaña es inválido."
            )
        if current_allowed_sucursal_keys is not None:
            raise MarketingReactivationValidationError(
                "El alcance actual no permite revalidar la campaña global."
            )
        return None
    if (
        not isinstance(frozen_values, list)
        or not frozen_values
        or any(not isinstance(value, str) for value in frozen_values)
    ):
        raise MarketingReactivationValidationError(
            "El scope congelado de la campaña es inválido."
        )
    frozen_scope = tuple(sorted(set(frozen_values)))
    if current_allowed_sucursal_keys is not None and not set(
        frozen_scope
    ).issubset(current_allowed_sucursal_keys):
        raise MarketingReactivationValidationError(
            "La campaña incluye sucursales fuera del alcance actual."
        )
    return frozen_scope


def _validate_frozen_campaign_recipients_scope(
    *,
    recipients: Any,
    effective_scope: tuple[str, ...] | None,
) -> None:
    if effective_scope is None:
        return
    allowed = set(effective_scope)
    outside_scope = {
        str(recipient.sucursal)
        for recipient in recipients
        if normalize_socios_vencidos_branch_key(recipient.sucursal) not in allowed
    }
    if outside_scope:
        raise MarketingReactivationValidationError(
            "La campaña contiene destinatarios fuera de su scope congelado."
        )


def _validate_optional_tariff_group(value: Any, field_name: str) -> str | None:
    normalized = _validate_optional_text(value, field_name, max_length=64)
    if normalized is not None and normalized not in _TARIFF_GROUPS:
        raise MarketingReactivationValidationError(
            f"{field_name} no es válido."
        )
    return normalized


def _matches_campaign_filters(
    row: dict[str, Any],
    filters: dict[str, Any],
) -> bool:
    if filters["sucursal"] and row["sucursal"] != filters["sucursal"]:
        return False
    if filters["tarifa"] and row["tarifa"] != filters["tarifa"]:
        return False
    operational_status = _operational_status(row)
    requested_status = filters["operational_status"]
    if requested_status == FILTER_WORK_PENDING and operational_status in {
        OPERATIONAL_ACTIVE,
        OPERATIONAL_CONTACTED_AFTER_EXPIRATION,
    }:
        return False
    if requested_status not in {FILTER_ALL, FILTER_WORK_PENDING} and (
        operational_status != requested_status
    ):
        return False
    search = _normalize_search(filters["search"])
    if search and not any(
        search in _normalize_search(value)
        for value in (row["nombre"], row["pin"], row["telefono"])
    ):
        return False
    return True


def _operational_status(row: dict[str, Any]) -> str:
    if row["status"] == "EXCLUDED_ACTIVE":
        return OPERATIONAL_ACTIVE
    if row["status"] == "REVIEW_ACTIVE_MATCH" or row["reason"] in {
        *_IDENTITY_REASONS,
        "NO_MX10",
        "DUPLICATE_VENCIDO_PHONE",
    }:
        return OPERATIONAL_REVIEW_IDENTITY
    if row["reason"] == "NO_MATCH_CURRENT_IVENTAS_RUN":
        return OPERATIONAL_NO_CONTACT_IN_PERIOD
    if row["reason"] == "NO_OUTBOUND_EVIDENCE":
        return OPERATIONAL_NO_OUTBOUND_MESSAGE
    if row["reason"] == "ONLY_PRE_EXPIRATION_OUTBOUND":
        return OPERATIONAL_CONTACTED_BEFORE_EXPIRATION
    if row["status"] == "EXCLUDED_POST_EXPIRATION_CONTACT":
        return OPERATIONAL_CONTACTED_AFTER_EXPIRATION
    return OPERATIONAL_REVIEW_IDENTITY


def _serialize_candidate(
    *,
    candidate: Any,
    vencido_row: Any,
    tariff_catalog: dict[str, MarketingReactivationTariffORM],
) -> dict[str, object]:
    tariff = tariff_catalog.get(
        normalize_reactivation_tariff_key(vencido_row.tarifa)
    )
    return {
        "vencido_row_id": int(candidate.vencido_row_id),
        "pin": str(vencido_row.pin),
        "nombre": vencido_row.nombre,
        "sucursal": vencido_row.sucursal_raw,
        "telefono": vencido_row.telefono_raw,
        "correo": vencido_row.correo_raw,
        "fecha_vencimiento": _serialize_date(vencido_row.fecha_vencimiento_date),
        "fecha_ultimo_pago": _serialize_optional_date(
            vencido_row.fecha_ultimo_pago_local
        ),
        "tarifa": vencido_row.tarifa,
        "tarifa_categoria": (
            str(tariff.categoria_tarifa) if tariff is not None else None
        ),
        "tarifa_group": (
            str(tariff.reactivation_group) if tariff is not None else None
        ),
        "tarifa_classified": tariff is not None,
        "adeudo": _serialize_optional_decimal(vencido_row.adeudo),
        "status": str(candidate.status),
        "reason": str(candidate.reason),
        "active_status": str(candidate.active_status),
        "active_id_socio": candidate.active_id_socio,
        "iventas_contact_id": candidate.iventas_contact_id,
        "latest_outbound_at_utc": _serialize_optional_aware_datetime(
            candidate.latest_outbound_at_utc
        ),
    }


def normalize_reactivation_tariff_key(value: Any) -> str | None:
    if value is None:
        return None
    normalized = unicodedata.normalize("NFKC", str(value)).strip().upper()
    normalized = " ".join(normalized.split())
    return normalized or None


def _read_active_tariff_catalog(
    *,
    tariff_values: Any,
    session: Any,
) -> dict[str, MarketingReactivationTariffORM]:
    tariff_keys = {
        key
        for key in (
            normalize_reactivation_tariff_key(value) for value in tariff_values
        )
        if key is not None
    }
    if not tariff_keys:
        return {}
    rows = (
        session.query(MarketingReactivationTariffORM)
        .filter(
            MarketingReactivationTariffORM.is_active.is_(True),
            MarketingReactivationTariffORM.tarifa_key.in_(
                tuple(sorted(tariff_keys))
            ),
        )
        .all()
    )
    return {str(row.tarifa_key): row for row in rows}


def _read_all_active_tariff_catalog(
    *,
    session: Any,
) -> dict[str, MarketingReactivationTariffORM]:
    rows = (
        session.query(MarketingReactivationTariffORM)
        .filter(MarketingReactivationTariffORM.is_active.is_(True))
        .all()
    )
    return {str(row.tarifa_key): row for row in rows}


def _serialize_tariff_classification(
    tariff: MarketingReactivationTariffORM | None,
) -> dict[str, object]:
    return {
        "classified": tariff is not None,
        "categoria_tarifa": (
            str(tariff.categoria_tarifa) if tariff is not None else None
        ),
        "reactivation_group": (
            str(tariff.reactivation_group) if tariff is not None else None
        ),
    }


def _serialize_campaign_recipient(row: Any) -> dict[str, object]:
    return {
        "id": int(row.id),
        "socios_vencidos_cartera_id": int(row.socios_vencidos_cartera_id),
        "phone_mx10": str(row.phone_mx10),
        "member_name": row.member_name,
        "sucursal": str(row.sucursal),
        "fecha_vencimiento_date": _serialize_date(row.fecha_vencimiento_date),
        "tarifa": row.tarifa,
        "inclusion_status": str(row.inclusion_status),
        "exclusion_reason": row.exclusion_reason,
        "operational_status": str(row.operational_status),
        "operational_reason": str(row.operational_reason),
        "created_at": _serialize_optional_aware_datetime(row.created_at),
    }


def _validate_date_range(
    date_from: date | str,
    date_to: date | str,
) -> tuple[date, date]:
    normalized_from = _ensure_date(date_from, "date_from")
    normalized_to = _ensure_date(date_to, "date_to")
    if normalized_from > normalized_to:
        raise MarketingReactivationValidationError(
            "date_from no puede ser posterior a date_to."
        )
    return normalized_from, normalized_to


def _ensure_date(value: date | str, field_name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value or ""))
    except ValueError as exc:
        raise MarketingReactivationValidationError(
            f"{field_name} debe ser una fecha ISO válida (YYYY-MM-DD)."
        ) from exc


def _validate_required_text(
    value: Any,
    field_name: str,
    *,
    max_length: int,
) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise MarketingReactivationValidationError(
            f"{field_name} es obligatorio."
        )
    if len(normalized) > max_length:
        raise MarketingReactivationValidationError(
            f"{field_name} no puede exceder {max_length} caracteres."
        )
    return normalized


def _validate_optional_text(
    value: Any,
    field_name: str,
    *,
    max_length: int,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise MarketingReactivationValidationError(
            f"{field_name} debe ser texto o null."
        )
    normalized = value.strip() or None
    if normalized is not None and len(normalized) > max_length:
        raise MarketingReactivationValidationError(
            f"{field_name} no puede exceder {max_length} caracteres."
        )
    return normalized


def _validate_now(value: datetime | None) -> datetime:
    now_value = value if value is not None else _utc_now()
    if now_value.tzinfo is None or now_value.utcoffset() is None:
        raise MarketingReactivationValidationError(
            "now debe incluir zona horaria."
        )
    return now_value.astimezone(timezone.utc)


def _normalize_search(value: Any) -> str:
    normalized = unicodedata.normalize(
        "NFD",
        str(value or "").strip().lower(),
    )
    return " ".join(
        "".join(
            character
            for character in normalized
            if not unicodedata.combining(character)
        ).split()
    )


def _serialize_date(value: date | datetime) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    return value.isoformat()


def _serialize_optional_date(value: date | datetime | None) -> str | None:
    return None if value is None else _serialize_date(value)


def _serialize_optional_decimal(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _serialize_optional_aware_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise SociosVencidosReactivationCandidateResolverError(
            "El datetime debe incluir zona horaria."
        )
    return value.isoformat()
