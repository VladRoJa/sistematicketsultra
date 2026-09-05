"""Resolución read-only de candidatos de reactivación.

El resolver combina el estado actual de Socios Vencidos con la
evidencia outbound del snapshot canónico iVentas. No interpreta la
ausencia de evidencia como elegibilidad y no modifica persistencia.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

from app.extensions import db
from app.models import MarketingIventasContactORM
from app.models.warehouse import (
    SociosVencidosCarteraORM,
    SociosVencidosSnapshotRowORM,
)
from app.services.marketing_iventas_leads_service import (
    read_canonical_iventas_run,
)
from app.services.marketing_iventas_service import (
    normalize_iventas_phone,
)
from app.warehouse.services.socios_vencidos_current_status_resolver import (
    STATUS_ACTIVE_CONFIRMED,
    STATUS_ACTIVE_REVIEW,
    STATUS_AMBIGUOUS,
    STATUS_IDENTIFIER_CONFLICT,
    STATUS_NOT_FOUND,
    SociosVencidosCurrentStatusContext,
    prepare_socios_vencidos_current_status_context,
    resolve_socios_vencidos_current_status,
    resolve_socios_vencidos_current_status_for_period,
    resolve_socios_vencidos_rows_with_context,
)


STATUS_EXCLUDED_ACTIVE = "EXCLUDED_ACTIVE"
STATUS_REVIEW_ACTIVE_MATCH = "REVIEW_ACTIVE_MATCH"
STATUS_EXCLUDED_POST_EXPIRATION_CONTACT = (
    "EXCLUDED_POST_EXPIRATION_CONTACT"
)
STATUS_CONTACT_HISTORY_UNKNOWN = (
    "CONTACT_HISTORY_UNKNOWN"
)

REASON_ACTIVE_CONFIRMED = STATUS_ACTIVE_CONFIRMED
REASON_ACTIVE_REVIEW = STATUS_ACTIVE_REVIEW
REASON_AMBIGUOUS = STATUS_AMBIGUOUS
REASON_IDENTIFIER_CONFLICT = STATUS_IDENTIFIER_CONFLICT
REASON_POST_EXPIRATION_OUTBOUND = (
    "POST_EXPIRATION_OUTBOUND"
)
REASON_NO_MX10 = "NO_MX10"
REASON_DUPLICATE_VENCIDO_PHONE = (
    "DUPLICATE_VENCIDO_PHONE"
)
REASON_NO_MATCH_CURRENT_IVENTAS_RUN = (
    "NO_MATCH_CURRENT_IVENTAS_RUN"
)
REASON_AMBIGUOUS_IVENTAS_IDENTITY = (
    "AMBIGUOUS_IVENTAS_IDENTITY"
)
REASON_NO_OUTBOUND_EVIDENCE = (
    "NO_OUTBOUND_EVIDENCE"
)
REASON_ONLY_PRE_EXPIRATION_OUTBOUND = (
    "ONLY_PRE_EXPIRATION_OUTBOUND"
)

_TIJUANA_TIMEZONE = ZoneInfo(
    "America/Tijuana"
)

_RESULT_STATUSES = (
    STATUS_EXCLUDED_ACTIVE,
    STATUS_REVIEW_ACTIVE_MATCH,
    STATUS_EXCLUDED_POST_EXPIRATION_CONTACT,
    STATUS_CONTACT_HISTORY_UNKNOWN,
)

_RESULT_REASONS = (
    REASON_ACTIVE_CONFIRMED,
    REASON_ACTIVE_REVIEW,
    REASON_AMBIGUOUS,
    REASON_IDENTIFIER_CONFLICT,
    REASON_POST_EXPIRATION_OUTBOUND,
    REASON_NO_MX10,
    REASON_DUPLICATE_VENCIDO_PHONE,
    REASON_NO_MATCH_CURRENT_IVENTAS_RUN,
    REASON_AMBIGUOUS_IVENTAS_IDENTITY,
    REASON_NO_OUTBOUND_EVIDENCE,
    REASON_ONLY_PRE_EXPIRATION_OUTBOUND,
)


class SociosVencidosReactivationCandidateResolverError(
    RuntimeError
):
    """El resolver no puede clasificar todas las filas con certeza."""


@dataclass(frozen=True, slots=True)
class SocioVencidoReactivationCandidate:
    vencido_row_id: int
    status: str
    reason: str
    active_status: str
    active_id_socio: str | None
    iventas_sync_run_id: int
    iventas_contact_id: str | None
    latest_outbound_at_utc: datetime | None


@dataclass(frozen=True, slots=True)
class SociosVencidosReactivationCandidateResult:
    vencidos_snapshot_id: int
    activos_snapshot_id: int
    iventas_sync_run_id: int
    iventas_period_key: str
    total_rows: int
    status_counts: dict[str, int]
    reason_counts: dict[str, int]
    rows: tuple[
        SocioVencidoReactivationCandidate,
        ...,
    ]


@dataclass(frozen=True, slots=True)
class SociosVencidosReactivationCandidatePeriodResult:
    date_from: str
    date_to: str
    activos_snapshot_id: int
    iventas_sync_run_id: int
    iventas_period_key: str
    total_rows: int
    status_counts: dict[str, int]
    reason_counts: dict[str, int]
    rows: tuple[SocioVencidoReactivationCandidate, ...]


@dataclass(frozen=True, slots=True)
class _CandidateResolution:
    activos_snapshot_id: int
    iventas_sync_run_id: int
    iventas_period_key: str
    total_rows: int
    status_counts: dict[str, int]
    reason_counts: dict[str, int]
    rows: tuple[SocioVencidoReactivationCandidate, ...]


@dataclass(frozen=True, slots=True)
class SociosVencidosReactivationResolutionContext:
    current_status: SociosVencidosCurrentStatusContext
    iventas_sync_run_id: int
    iventas_period_key: str


def resolve_socios_vencidos_reactivation_candidates(
    *,
    vencidos_snapshot_id: int,
    iventas_period_key: str,
    activos_snapshot_id: int | None = None,
    session: Any | None = None,
) -> SociosVencidosReactivationCandidateResult:
    """Clasifica vencidos sin persistir ni inferir elegibilidad."""
    session_value = session if session is not None else db.session
    current_status_result = resolve_socios_vencidos_current_status(
        vencidos_snapshot_id=vencidos_snapshot_id,
        activos_snapshot_id=activos_snapshot_id,
        session=session_value,
    )
    resolution = _resolve_candidates_from_current_status(
        current_status_result=current_status_result,
        iventas_period_key=iventas_period_key,
        vencido_rows_reader=lambda row_ids: _read_vencido_rows(
            vencidos_snapshot_id=int(current_status_result.vencidos_snapshot_id),
            vencido_row_ids=row_ids,
            session=session_value,
        ),
        session=session_value,
    )
    result = SociosVencidosReactivationCandidateResult(
        vencidos_snapshot_id=int(current_status_result.vencidos_snapshot_id),
        activos_snapshot_id=resolution.activos_snapshot_id,
        iventas_sync_run_id=resolution.iventas_sync_run_id,
        iventas_period_key=resolution.iventas_period_key,
        total_rows=resolution.total_rows,
        status_counts=resolution.status_counts,
        reason_counts=resolution.reason_counts,
        rows=resolution.rows,
    )
    _validate_result_invariants(result)
    return result


def resolve_socios_vencidos_reactivation_candidates_for_period(
    *,
    date_from: date | datetime | str,
    date_to: date | datetime | str,
    iventas_period_key: str,
    activos_snapshot_id: int | None = None,
    session: Any | None = None,
) -> SociosVencidosReactivationCandidatePeriodResult:
    session_value = session if session is not None else db.session
    current_status_result = resolve_socios_vencidos_current_status_for_period(
        date_from=date_from,
        date_to=date_to,
        activos_snapshot_id=activos_snapshot_id,
        session=session_value,
    )
    resolution = _resolve_candidates_from_current_status(
        current_status_result=current_status_result,
        iventas_period_key=iventas_period_key,
        vencido_rows_reader=lambda row_ids: _read_cartera_rows(
            vencido_row_ids=row_ids,
            session=session_value,
        ),
        session=session_value,
    )
    result = SociosVencidosReactivationCandidatePeriodResult(
        date_from=current_status_result.date_from,
        date_to=current_status_result.date_to,
        activos_snapshot_id=resolution.activos_snapshot_id,
        iventas_sync_run_id=resolution.iventas_sync_run_id,
        iventas_period_key=resolution.iventas_period_key,
        total_rows=resolution.total_rows,
        status_counts=resolution.status_counts,
        reason_counts=resolution.reason_counts,
        rows=resolution.rows,
    )
    _validate_result_invariants(result)
    return result


def prepare_socios_vencidos_reactivation_resolution_context(
    *,
    minimum_cutoff_date: date,
    iventas_period_key: str,
    activos_snapshot_id: int | None = None,
    session: Any | None = None,
) -> SociosVencidosReactivationResolutionContext:
    session_value = session if session is not None else db.session
    current_context = prepare_socios_vencidos_current_status_context(
        minimum_cutoff_date=minimum_cutoff_date,
        activos_snapshot_id=activos_snapshot_id,
        session=session_value,
    )
    canonical_run = read_canonical_iventas_run(
        period_key=iventas_period_key,
        session=session_value,
    )
    return SociosVencidosReactivationResolutionContext(
        current_status=current_context,
        iventas_sync_run_id=int(canonical_run["sync_run_id"]),
        iventas_period_key=str(canonical_run["period_key"]),
    )


def resolve_socios_vencidos_reactivation_candidate_batch(
    *,
    vencidos_rows: list[Any] | tuple[Any, ...],
    context: SociosVencidosReactivationResolutionContext,
    phone_counts: Counter[str],
    current_rows: tuple[Any, ...] | None = None,
    session: Any | None = None,
) -> tuple[SocioVencidoReactivationCandidate, ...]:
    """Resuelve un lote conservando duplicados del universo completo."""

    session_value = session if session is not None else db.session
    if current_rows is None:
        current_rows = resolve_socios_vencidos_rows_with_context(
            vencidos_rows=vencidos_rows,
            context=context.current_status,
        )
    elif {int(row.vencido_row_id) for row in current_rows} != {
        int(row.id) for row in vencidos_rows
    }:
        raise SociosVencidosReactivationCandidateResolverError(
            "Las filas de estado actual no corresponden al lote vencido."
        )
    current_by_id = {int(row.vencido_row_id): row for row in current_rows}
    source_by_id = {int(row.id): row for row in vencidos_rows}
    not_found_ids = {
        row_id
        for row_id, row in current_by_id.items()
        if row.status == STATUS_NOT_FOUND
    }
    phone_by_id = {
        row_id: normalize_iventas_phone(
            source_by_id[row_id].telefono_raw
        ).phone_mx10
        for row_id in not_found_ids
    }
    contacts_by_phone = _read_iventas_contacts(
        iventas_sync_run_id=context.iventas_sync_run_id,
        phone_mx10_values={
            phone
            for phone in phone_by_id.values()
            if phone is not None and phone_counts[phone] == 1
        },
        session=session_value,
    )
    resolved = []
    for row_id, current_row in current_by_id.items():
        if current_row.status == STATUS_ACTIVE_CONFIRMED:
            resolved.append(_build_active_candidate(
                current_row=current_row,
                iventas_sync_run_id=context.iventas_sync_run_id,
                status=STATUS_EXCLUDED_ACTIVE,
                reason=REASON_ACTIVE_CONFIRMED,
            ))
            continue
        if current_row.status in {
            STATUS_ACTIVE_REVIEW,
            STATUS_AMBIGUOUS,
            STATUS_IDENTIFIER_CONFLICT,
        }:
            resolved.append(_build_active_candidate(
                current_row=current_row,
                iventas_sync_run_id=context.iventas_sync_run_id,
                status=STATUS_REVIEW_ACTIVE_MATCH,
                reason=current_row.status,
            ))
            continue
        if current_row.status != STATUS_NOT_FOUND:
            raise SociosVencidosReactivationCandidateResolverError(
                f"Estado actual no reconocido para vencido_row_id={row_id}: "
                f"{current_row.status!r}."
            )
        phone = phone_by_id[row_id]
        resolved.append(_build_not_found_candidate(
            current_row=current_row,
            vencido_row=source_by_id[row_id],
            phone_mx10=phone,
            duplicate_phone=(
                phone is not None and phone_counts[phone] > 1
            ),
            contacts=(
                contacts_by_phone.get(phone, tuple())
                if phone is not None
                else tuple()
            ),
            iventas_sync_run_id=context.iventas_sync_run_id,
        ))
    return tuple(resolved)


def count_socios_vencidos_not_found_phones(
    *,
    vencidos_rows: list[Any] | tuple[Any, ...],
    context: SociosVencidosReactivationResolutionContext,
) -> Counter[str]:
    """Cuenta teléfonos sólo en filas sin match activo, como el resolver original."""

    current_rows = resolve_socios_vencidos_rows_with_context(
        vencidos_rows=vencidos_rows,
        context=context.current_status,
    )
    source_by_id = {int(row.id): row for row in vencidos_rows}
    return Counter(
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


def _resolve_candidates_from_current_status(
    *,
    current_status_result: Any,
    iventas_period_key: str,
    vencido_rows_reader: Callable[[set[int]], dict[int, Any]],
    session: Any,
) -> _CandidateResolution:
    canonical_run = read_canonical_iventas_run(
        period_key=iventas_period_key,
        session=session,
    )
    iventas_sync_run_id = int(canonical_run["sync_run_id"])
    canonical_period_key = str(canonical_run["period_key"])
    current_rows = tuple(current_status_result.rows)
    if len(current_rows) != current_status_result.total_rows:
        raise SociosVencidosReactivationCandidateResolverError(
            "El resultado de estado actual tiene un total_rows inconsistente."
        )

    not_found_rows = tuple(
        row for row in current_rows if row.status == STATUS_NOT_FOUND
    )
    vencido_rows_by_id = vencido_rows_reader(
        {int(row.vencido_row_id) for row in not_found_rows}
    )
    phone_by_vencido_row_id = {
        int(row.vencido_row_id): normalize_iventas_phone(
            vencido_rows_by_id[int(row.vencido_row_id)].telefono_raw
        ).phone_mx10
        for row in not_found_rows
    }
    phone_counts = Counter(
        phone for phone in phone_by_vencido_row_id.values() if phone is not None
    )
    contacts_by_phone = _read_iventas_contacts(
        iventas_sync_run_id=iventas_sync_run_id,
        phone_mx10_values={
            phone for phone, count in phone_counts.items() if count == 1
        },
        session=session,
    )

    resolved_rows: list[SocioVencidoReactivationCandidate] = []
    for current_row in current_rows:
        if current_row.status == STATUS_ACTIVE_CONFIRMED:
            resolved_rows.append(_build_active_candidate(
                current_row=current_row,
                iventas_sync_run_id=iventas_sync_run_id,
                status=STATUS_EXCLUDED_ACTIVE,
                reason=REASON_ACTIVE_CONFIRMED,
            ))
            continue
        if current_row.status in {
            STATUS_ACTIVE_REVIEW,
            STATUS_AMBIGUOUS,
            STATUS_IDENTIFIER_CONFLICT,
        }:
            resolved_rows.append(_build_active_candidate(
                current_row=current_row,
                iventas_sync_run_id=iventas_sync_run_id,
                status=STATUS_REVIEW_ACTIVE_MATCH,
                reason=current_row.status,
            ))
            continue
        if current_row.status != STATUS_NOT_FOUND:
            raise SociosVencidosReactivationCandidateResolverError(
                "Estado actual no reconocido para "
                f"vencido_row_id={current_row.vencido_row_id}: "
                f"{current_row.status!r}."
            )

        row_id = int(current_row.vencido_row_id)
        phone_mx10 = phone_by_vencido_row_id[row_id]
        resolved_rows.append(_build_not_found_candidate(
            current_row=current_row,
            vencido_row=vencido_rows_by_id[row_id],
            phone_mx10=phone_mx10,
            duplicate_phone=(
                phone_mx10 is not None and phone_counts[phone_mx10] > 1
            ),
            contacts=(
                contacts_by_phone.get(phone_mx10, tuple())
                if phone_mx10 is not None
                else tuple()
            ),
            iventas_sync_run_id=iventas_sync_run_id,
        ))

    rows = tuple(resolved_rows)
    status_counter = Counter(row.status for row in rows)
    reason_counter = Counter(row.reason for row in rows)
    return _CandidateResolution(
        activos_snapshot_id=int(current_status_result.activos_snapshot_id),
        iventas_sync_run_id=iventas_sync_run_id,
        iventas_period_key=canonical_period_key,
        total_rows=int(current_status_result.total_rows),
        status_counts={status: status_counter[status] for status in _RESULT_STATUSES},
        reason_counts={reason: reason_counter[reason] for reason in _RESULT_REASONS},
        rows=rows,
    )


def _read_vencido_rows(
    *,
    vencidos_snapshot_id: int,
    vencido_row_ids: set[int],
    session: Any,
) -> dict[int, Any]:
    if not vencido_row_ids:
        return {}

    rows = (
        session.query(
            SociosVencidosSnapshotRowORM
        )
        .filter(
            SociosVencidosSnapshotRowORM.snapshot_id
            == vencidos_snapshot_id,
            SociosVencidosSnapshotRowORM.id.in_(
                tuple(
                    sorted(vencido_row_ids)
                )
            ),
        )
        .all()
    )

    rows_by_id = {
        int(row.id): row
        for row in rows
    }

    missing_ids = (
        vencido_row_ids
        - rows_by_id.keys()
    )

    if missing_ids:
        raise (
            SociosVencidosReactivationCandidateResolverError(
                "No se encontraron filas NOT_FOUND del "
                "snapshot de vencidos: "
                f"{sorted(missing_ids)}."
            )
        )

    return rows_by_id


def _read_cartera_rows(
    *,
    vencido_row_ids: set[int],
    session: Any,
) -> dict[int, Any]:
    if not vencido_row_ids:
        return {}

    rows = (
        session.query(SociosVencidosCarteraORM)
        .filter(
            SociosVencidosCarteraORM.id.in_(
                tuple(sorted(vencido_row_ids))
            )
        )
        .all()
    )
    rows_by_id = {int(row.id): row for row in rows}
    missing_ids = vencido_row_ids - rows_by_id.keys()
    if missing_ids:
        raise SociosVencidosReactivationCandidateResolverError(
            "No se encontraron episodios NOT_FOUND de cartera: "
            f"{sorted(missing_ids)}."
        )
    return rows_by_id


def _read_iventas_contacts(
    *,
    iventas_sync_run_id: int,
    phone_mx10_values: set[str],
    session: Any,
) -> dict[str, tuple[Any, ...]]:
    if not phone_mx10_values:
        return {}

    rows = (
        session.query(
            MarketingIventasContactORM
        )
        .filter(
            MarketingIventasContactORM.sync_run_id
            == iventas_sync_run_id,
            MarketingIventasContactORM.phone_mx10.in_(
                tuple(
                    sorted(phone_mx10_values)
                )
            ),
        )
        .all()
    )

    contacts_by_phone: dict[
        str,
        list[Any],
    ] = defaultdict(list)

    for row in rows:
        phone_mx10 = str(
            row.phone_mx10
        )

        if phone_mx10 in phone_mx10_values:
            contacts_by_phone[
                phone_mx10
            ].append(row)

    return {
        phone_mx10: tuple(contacts)
        for phone_mx10, contacts
        in contacts_by_phone.items()
    }


def _build_active_candidate(
    *,
    current_row: Any,
    iventas_sync_run_id: int,
    status: str,
    reason: str,
) -> SocioVencidoReactivationCandidate:
    return SocioVencidoReactivationCandidate(
        vencido_row_id=int(
            current_row.vencido_row_id
        ),
        status=status,
        reason=reason,
        active_status=str(
            current_row.status
        ),
        active_id_socio=(
            current_row.active_id_socio
        ),
        iventas_sync_run_id=(
            iventas_sync_run_id
        ),
        iventas_contact_id=None,
        latest_outbound_at_utc=None,
    )


def _build_not_found_candidate(
    *,
    current_row: Any,
    vencido_row: Any,
    phone_mx10: str | None,
    duplicate_phone: bool,
    contacts: tuple[Any, ...],
    iventas_sync_run_id: int,
) -> SocioVencidoReactivationCandidate:
    if phone_mx10 is None:
        return _build_unknown_candidate(
            current_row=current_row,
            iventas_sync_run_id=(
                iventas_sync_run_id
            ),
            reason=REASON_NO_MX10,
        )

    if duplicate_phone:
        return _build_unknown_candidate(
            current_row=current_row,
            iventas_sync_run_id=(
                iventas_sync_run_id
            ),
            reason=(
                REASON_DUPLICATE_VENCIDO_PHONE
            ),
        )

    if not contacts:
        return _build_unknown_candidate(
            current_row=current_row,
            iventas_sync_run_id=(
                iventas_sync_run_id
            ),
            reason=(
                REASON_NO_MATCH_CURRENT_IVENTAS_RUN
            ),
        )

    contact_ids = {
        str(contact.contact_id)
        for contact in contacts
    }

    if len(contact_ids) != 1:
        return _build_unknown_candidate(
            current_row=current_row,
            iventas_sync_run_id=(
                iventas_sync_run_id
            ),
            reason=(
                REASON_AMBIGUOUS_IVENTAS_IDENTITY
            ),
        )

    iventas_contact_id = next(
        iter(contact_ids)
    )

    outbound_values = tuple(
        _as_aware_utc(
            contact.last_outbound_message_at_utc
        )
        for contact in contacts
        if (
            contact.last_outbound_message_at_utc
            is not None
        )
    )

    if not outbound_values:
        return _build_unknown_candidate(
            current_row=current_row,
            iventas_sync_run_id=(
                iventas_sync_run_id
            ),
            reason=REASON_NO_OUTBOUND_EVIDENCE,
            iventas_contact_id=(
                iventas_contact_id
            ),
        )

    latest_outbound_at_utc = max(
        outbound_values
    )
    expiration_date = _read_expiration_date(
        vencido_row
    )
    latest_outbound_local_date = (
        latest_outbound_at_utc
        .astimezone(
            _TIJUANA_TIMEZONE
        )
        .date()
    )

    if (
        latest_outbound_local_date
        >= expiration_date
    ):
        return SocioVencidoReactivationCandidate(
            vencido_row_id=int(
                current_row.vencido_row_id
            ),
            status=(
                STATUS_EXCLUDED_POST_EXPIRATION_CONTACT
            ),
            reason=(
                REASON_POST_EXPIRATION_OUTBOUND
            ),
            active_status=str(
                current_row.status
            ),
            active_id_socio=(
                current_row.active_id_socio
            ),
            iventas_sync_run_id=(
                iventas_sync_run_id
            ),
            iventas_contact_id=(
                iventas_contact_id
            ),
            latest_outbound_at_utc=(
                latest_outbound_at_utc
            ),
        )

    return _build_unknown_candidate(
        current_row=current_row,
        iventas_sync_run_id=(
            iventas_sync_run_id
        ),
        reason=(
            REASON_ONLY_PRE_EXPIRATION_OUTBOUND
        ),
        iventas_contact_id=(
            iventas_contact_id
        ),
        latest_outbound_at_utc=(
            latest_outbound_at_utc
        ),
    )


def _build_unknown_candidate(
    *,
    current_row: Any,
    iventas_sync_run_id: int,
    reason: str,
    iventas_contact_id: str | None = None,
    latest_outbound_at_utc: datetime | None = None,
) -> SocioVencidoReactivationCandidate:
    return SocioVencidoReactivationCandidate(
        vencido_row_id=int(
            current_row.vencido_row_id
        ),
        status=STATUS_CONTACT_HISTORY_UNKNOWN,
        reason=reason,
        active_status=str(
            current_row.status
        ),
        active_id_socio=(
            current_row.active_id_socio
        ),
        iventas_sync_run_id=(
            iventas_sync_run_id
        ),
        iventas_contact_id=(
            iventas_contact_id
        ),
        latest_outbound_at_utc=(
            latest_outbound_at_utc
        ),
    )


def _as_aware_utc(
    value: Any,
) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise (
            SociosVencidosReactivationCandidateResolverError(
                "last_outbound_message_at_utc debe ser "
                "timezone-aware."
            )
        )

    return value.astimezone(
        timezone.utc
    )


def _read_expiration_date(
    vencido_row: Any,
) -> date:
    value = getattr(
        vencido_row,
        "fecha_vencimiento_date",
        None,
    )

    if (
        not isinstance(value, date)
        or isinstance(value, datetime)
    ):
        raise (
            SociosVencidosReactivationCandidateResolverError(
                "fecha_vencimiento_date debe ser una fecha."
            )
        )

    return value


def _validate_result_invariants(
    result: SociosVencidosReactivationCandidateResult,
) -> None:
    if (
        len(result.rows) != result.total_rows
        or sum(
            result.status_counts.values()
        ) != result.total_rows
        or sum(
            result.reason_counts.values()
        ) != result.total_rows
    ):
        raise (
            SociosVencidosReactivationCandidateResolverError(
                "El resultado de candidatos viola sus "
                "invariantes de cardinalidad."
            )
        )
