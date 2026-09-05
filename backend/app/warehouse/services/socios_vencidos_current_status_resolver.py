from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
import re
import unicodedata

from app.extensions import db
from app.models.warehouse import (
    SociosActivosSnapshotORM,
    SociosActivosSnapshotRowORM,
    SociosVencidosCarteraORM,
    SociosVencidosSnapshotORM,
    SociosVencidosSnapshotRowORM,
)

from app.warehouse.services.socios_activos_snapshot_resolver import (
    resolve_latest_canonical_socios_activos_snapshot,
)


STATUS_ACTIVE_CONFIRMED = "ACTIVE_CONFIRMED"
STATUS_ACTIVE_REVIEW = "ACTIVE_REVIEW"
STATUS_AMBIGUOUS = "AMBIGUOUS"
STATUS_IDENTIFIER_CONFLICT = "IDENTIFIER_CONFLICT"
STATUS_NOT_FOUND = "NOT_FOUND"

SIGNAL_BRANCH_PIN = "branch_pin"
SIGNAL_PHONE = "phone"
SIGNAL_EMAIL = "email"


class SociosVencidosCurrentStatusResolverError(RuntimeError):
    """Error al resolver estado actual de socios vencidos."""


@dataclass(frozen=True, slots=True)
class SocioVencidoCurrentStatus:
    vencido_row_id: int
    status: str
    active_id_socio: str | None
    matched_signals: tuple[str, ...] = field(
        default_factory=tuple
    )
    branch_pin_candidate_count: int = 0
    phone_candidate_count: int = 0
    email_candidate_count: int = 0


@dataclass(frozen=True, slots=True)
class SociosVencidosCurrentStatusResult:
    vencidos_snapshot_id: int
    activos_snapshot_id: int
    vencidos_date_to: str
    activos_cutoff_date: str
    total_rows: int
    status_counts: dict[str, int]
    rows: tuple[SocioVencidoCurrentStatus, ...]


@dataclass(frozen=True, slots=True)
class SociosVencidosCurrentStatusPeriodResult:
    date_from: str
    date_to: str
    activos_snapshot_id: int
    activos_cutoff_date: str
    total_rows: int
    status_counts: dict[str, int]
    rows: tuple[SocioVencidoCurrentStatus, ...]


@dataclass(frozen=True, slots=True)
class SociosVencidosCurrentStatusContext:
    activos_snapshot_id: int
    activos_cutoff_date: str
    indexes: dict[str, dict[Any, set[str]]]


def resolve_socios_vencidos_current_status(
    *,
    vencidos_snapshot_id: int,
    activos_snapshot_id: int | None = None,
    session: Any | None = None,
) -> SociosVencidosCurrentStatusResult:
    normalized_vencidos_snapshot_id = _ensure_positive_int(
        vencidos_snapshot_id,
        field_name="vencidos_snapshot_id",
    )
    normalized_activos_snapshot_id = (
        _ensure_positive_int(
            activos_snapshot_id,
            field_name="activos_snapshot_id",
        )
        if activos_snapshot_id is not None
        else None
    )

    active_session = (
        session
        if session is not None
        else db.session
    )

    vencidos_snapshot = (
        active_session.query(
            SociosVencidosSnapshotORM
        )
        .filter(
            SociosVencidosSnapshotORM.id
            == normalized_vencidos_snapshot_id
        )
        .one_or_none()
    )

    if vencidos_snapshot is None:
        raise SociosVencidosCurrentStatusResolverError(
            "No existe el snapshot de socios vencidos "
            f"id={normalized_vencidos_snapshot_id}."
        )

    activos_snapshot = _resolve_activos_snapshot_for_vencidos(
        vencidos_snapshot=vencidos_snapshot,
        activos_snapshot_id=normalized_activos_snapshot_id,
        active_session=active_session,
    )

    if (
        activos_snapshot.cutoff_date
        < vencidos_snapshot.date_to
    ):
        raise SociosVencidosCurrentStatusResolverError(
            "El snapshot de socios activos es anterior "
            "al periodo vencido que se intenta resolver."
        )

    vencidos_rows = (
        active_session.query(
            SociosVencidosSnapshotRowORM
        )
        .filter(
            SociosVencidosSnapshotRowORM.snapshot_id
            == normalized_vencidos_snapshot_id
        )
        .order_by(
            SociosVencidosSnapshotRowORM.row_index.asc()
        )
        .all()
    )

    activos_rows = (
        active_session.query(
            SociosActivosSnapshotRowORM
        )
        .filter(
            SociosActivosSnapshotRowORM.snapshot_id
            == int(activos_snapshot.id)
        )
        .all()
    )

    resolved_rows, status_counts = _resolve_rows_against_activos(
        vencidos_rows=vencidos_rows,
        activos_rows=activos_rows,
    )

    return SociosVencidosCurrentStatusResult(
        vencidos_snapshot_id=(
            normalized_vencidos_snapshot_id
        ),
        activos_snapshot_id=int(
            activos_snapshot.id
        ),
        vencidos_date_to=(
            vencidos_snapshot.date_to.isoformat()
        ),
        activos_cutoff_date=(
            activos_snapshot.cutoff_date.isoformat()
        ),
        total_rows=len(resolved_rows),
        status_counts=status_counts,
        rows=resolved_rows,
    )


def resolve_socios_vencidos_current_status_for_period(
    *,
    date_from: date | datetime | str,
    date_to: date | datetime | str,
    activos_snapshot_id: int | None = None,
    session: Any | None = None,
) -> SociosVencidosCurrentStatusPeriodResult:
    normalized_date_from = _ensure_date(date_from, field_name="date_from")
    normalized_date_to = _ensure_date(date_to, field_name="date_to")
    if normalized_date_from > normalized_date_to:
        raise ValueError("date_from no puede ser posterior a date_to.")

    normalized_activos_snapshot_id = (
        _ensure_positive_int(activos_snapshot_id, field_name="activos_snapshot_id")
        if activos_snapshot_id is not None
        else None
    )
    active_session = session if session is not None else db.session
    activos_snapshot = _resolve_activos_snapshot(
        minimum_cutoff_date=normalized_date_to,
        activos_snapshot_id=normalized_activos_snapshot_id,
        active_session=active_session,
    )
    if activos_snapshot.cutoff_date < normalized_date_to:
        raise SociosVencidosCurrentStatusResolverError(
            "El snapshot de socios activos es anterior al periodo vencido "
            "que se intenta resolver."
        )

    vencidos_rows = (
        active_session.query(SociosVencidosCarteraORM)
        .filter(
            SociosVencidosCarteraORM.fecha_vencimiento_date.between(
                normalized_date_from,
                normalized_date_to,
            )
        )
        .order_by(
            SociosVencidosCarteraORM.fecha_vencimiento_date.asc(),
            SociosVencidosCarteraORM.id.asc(),
        )
        .all()
    )
    activos_rows = (
        active_session.query(SociosActivosSnapshotRowORM)
        .filter(
            SociosActivosSnapshotRowORM.snapshot_id
            == int(activos_snapshot.id)
        )
        .all()
    )
    resolved_rows, status_counts = _resolve_rows_against_activos(
        vencidos_rows=vencidos_rows,
        activos_rows=activos_rows,
    )
    return SociosVencidosCurrentStatusPeriodResult(
        date_from=normalized_date_from.isoformat(),
        date_to=normalized_date_to.isoformat(),
        activos_snapshot_id=int(activos_snapshot.id),
        activos_cutoff_date=activos_snapshot.cutoff_date.isoformat(),
        total_rows=len(resolved_rows),
        status_counts=status_counts,
        rows=resolved_rows,
    )


def prepare_socios_vencidos_current_status_context(
    *,
    minimum_cutoff_date: date,
    activos_snapshot_id: int | None = None,
    session: Any | None = None,
) -> SociosVencidosCurrentStatusContext:
    """Carga una vez el snapshot activo para resolver lotes de cartera."""

    active_session = session if session is not None else db.session
    snapshot = _resolve_activos_snapshot(
        minimum_cutoff_date=minimum_cutoff_date,
        activos_snapshot_id=activos_snapshot_id,
        active_session=active_session,
    )
    if snapshot.cutoff_date < minimum_cutoff_date:
        raise SociosVencidosCurrentStatusResolverError(
            "El snapshot de socios activos es anterior al periodo vencido "
            "que se intenta resolver."
        )
    rows = (
        active_session.query(SociosActivosSnapshotRowORM)
        .filter(
            SociosActivosSnapshotRowORM.snapshot_id == int(snapshot.id)
        )
        .all()
    )
    return SociosVencidosCurrentStatusContext(
        activos_snapshot_id=int(snapshot.id),
        activos_cutoff_date=snapshot.cutoff_date.isoformat(),
        indexes=_build_active_indexes(rows),
    )


def resolve_socios_vencidos_rows_with_context(
    *,
    vencidos_rows: list[Any] | tuple[Any, ...],
    context: SociosVencidosCurrentStatusContext,
) -> tuple[SocioVencidoCurrentStatus, ...]:
    """Aplica sin I/O el matcher vigente a un lote de episodios."""

    return tuple(
        _resolve_vencido_row(row, indexes=context.indexes)
        for row in vencidos_rows
    )


def _resolve_rows_against_activos(
    *,
    vencidos_rows: list[Any],
    activos_rows: list[Any],
) -> tuple[tuple[SocioVencidoCurrentStatus, ...], dict[str, int]]:
    indexes = _build_active_indexes(activos_rows)
    resolved_rows = tuple(
        _resolve_vencido_row(row, indexes=indexes)
        for row in vencidos_rows
    )
    counts = Counter(row.status for row in resolved_rows)
    return resolved_rows, {
        STATUS_ACTIVE_CONFIRMED: counts[STATUS_ACTIVE_CONFIRMED],
        STATUS_ACTIVE_REVIEW: counts[STATUS_ACTIVE_REVIEW],
        STATUS_AMBIGUOUS: counts[STATUS_AMBIGUOUS],
        STATUS_IDENTIFIER_CONFLICT: counts[STATUS_IDENTIFIER_CONFLICT],
        STATUS_NOT_FOUND: counts[STATUS_NOT_FOUND],
    }



def _resolve_activos_snapshot_for_vencidos(
    *,
    vencidos_snapshot: SociosVencidosSnapshotORM,
    activos_snapshot_id: int | None,
    active_session: Any,
) -> SociosActivosSnapshotORM:
    return _resolve_activos_snapshot(
        minimum_cutoff_date=vencidos_snapshot.date_to,
        activos_snapshot_id=activos_snapshot_id,
        active_session=active_session,
    )


def _resolve_activos_snapshot(
    *,
    minimum_cutoff_date: date,
    activos_snapshot_id: int | None,
    active_session: Any,
) -> SociosActivosSnapshotORM:
    if activos_snapshot_id is not None:
        snapshot = (
            active_session.query(
                SociosActivosSnapshotORM
            )
            .filter(
                SociosActivosSnapshotORM.id
                == activos_snapshot_id
            )
            .one_or_none()
        )

        if snapshot is None:
            raise SociosVencidosCurrentStatusResolverError(
                "No existe el snapshot de socios activos "
                f"id={activos_snapshot_id}."
            )

        return snapshot

    snapshot = (
        resolve_latest_canonical_socios_activos_snapshot(
            minimum_cutoff_date=minimum_cutoff_date,
            session=active_session,
        )
    )

    if snapshot is None:
        raise SociosVencidosCurrentStatusResolverError(
            "No existe un snapshot canónico de Socios Activos "
            "con cutoff_date igual o posterior a "
            f"{minimum_cutoff_date.isoformat()}."
        )

    return snapshot

def _build_active_indexes(
    activos_rows: list[Any],
) -> dict[str, dict[Any, set[str]]]:
    by_branch_pin: dict[
        tuple[str, str],
        set[str],
    ] = defaultdict(set)

    by_phone: dict[
        str,
        set[str],
    ] = defaultdict(set)

    by_email: dict[
        str,
        set[str],
    ] = defaultdict(set)

    for row in activos_rows:
        member_id = _normalize_required_id_socio(
            getattr(
                row,
                "id_socio",
                None,
            )
        )

        branch = normalize_socios_vencidos_branch_key(
            getattr(
                row,
                "sucursal_raw",
                None,
            )
        )

        pin = _normalize_pin(
            getattr(
                row,
                "pin",
                None,
            )
        )

        phone = _normalize_phone(
            getattr(
                row,
                "telefono_digits",
                None,
            )
        )

        email = _normalize_email(
            getattr(
                row,
                "email_raw",
                None,
            )
        )

        if branch and pin:
            by_branch_pin[
                (branch, pin)
            ].add(member_id)

        if phone:
            by_phone[
                phone
            ].add(member_id)

        if email:
            by_email[
                email
            ].add(member_id)

    return {
        SIGNAL_BRANCH_PIN: by_branch_pin,
        SIGNAL_PHONE: by_phone,
        SIGNAL_EMAIL: by_email,
    }


def _resolve_vencido_row(
    row: Any,
    *,
    indexes: dict[str, dict[Any, set[str]]],
) -> SocioVencidoCurrentStatus:
    branch = normalize_socios_vencidos_branch_key(
        getattr(
            row,
            "sucursal_raw",
            None,
        )
    )

    pin = _normalize_pin(
        getattr(
            row,
            "pin",
            None,
        )
    )

    phone = _normalize_phone(
        getattr(
            row,
            "telefono_digits",
            None,
        )
    )

    email = _normalize_email(
        getattr(
            row,
            "correo_raw",
            None,
        )
    )

    candidate_sets = {
        SIGNAL_BRANCH_PIN: (
            indexes[
                SIGNAL_BRANCH_PIN
            ].get(
                (branch, pin),
                set(),
            )
            if branch and pin
            else set()
        ),
        SIGNAL_PHONE: (
            indexes[
                SIGNAL_PHONE
            ].get(
                phone,
                set(),
            )
            if phone
            else set()
        ),
        SIGNAL_EMAIL: (
            indexes[
                SIGNAL_EMAIL
            ].get(
                email,
                set(),
            )
            if email
            else set()
        ),
    }

    unique_signals = {
        signal: next(
            iter(candidates)
        )
        for signal, candidates
        in candidate_sets.items()
        if len(candidates) == 1
    }

    unique_ids = set(
        unique_signals.values()
    )

    candidate_counts = {
        SIGNAL_BRANCH_PIN: len(
            candidate_sets[
                SIGNAL_BRANCH_PIN
            ]
        ),
        SIGNAL_PHONE: len(
            candidate_sets[
                SIGNAL_PHONE
            ]
        ),
        SIGNAL_EMAIL: len(
            candidate_sets[
                SIGNAL_EMAIL
            ]
        ),
    }

    vencido_row_id = int(
        getattr(
            row,
            "id",
        )
    )

    if len(unique_ids) > 1:
        return SocioVencidoCurrentStatus(
            vencido_row_id=vencido_row_id,
            status=STATUS_IDENTIFIER_CONFLICT,
            active_id_socio=None,
            matched_signals=tuple(
                sorted(
                    unique_signals.keys()
                )
            ),
            branch_pin_candidate_count=(
                candidate_counts[
                    SIGNAL_BRANCH_PIN
                ]
            ),
            phone_candidate_count=(
                candidate_counts[
                    SIGNAL_PHONE
                ]
            ),
            email_candidate_count=(
                candidate_counts[
                    SIGNAL_EMAIL
                ]
            ),
        )

    if len(unique_ids) == 1:
        matched_id = next(
            iter(unique_ids)
        )

        agreeing_signals = tuple(
            sorted(
                signal
                for signal, member_id
                in unique_signals.items()
                if member_id == matched_id
            )
        )

        confirmed = (
            SIGNAL_BRANCH_PIN
            in agreeing_signals
            or (
                SIGNAL_PHONE
                in agreeing_signals
                and SIGNAL_EMAIL
                in agreeing_signals
            )
        )

        status = (
            STATUS_ACTIVE_CONFIRMED
            if confirmed
            else STATUS_ACTIVE_REVIEW
        )

        return SocioVencidoCurrentStatus(
            vencido_row_id=vencido_row_id,
            status=status,
            active_id_socio=matched_id,
            matched_signals=agreeing_signals,
            branch_pin_candidate_count=(
                candidate_counts[
                    SIGNAL_BRANCH_PIN
                ]
            ),
            phone_candidate_count=(
                candidate_counts[
                    SIGNAL_PHONE
                ]
            ),
            email_candidate_count=(
                candidate_counts[
                    SIGNAL_EMAIL
                ]
            ),
        )

    if any(
        candidate_sets.values()
    ):
        return SocioVencidoCurrentStatus(
            vencido_row_id=vencido_row_id,
            status=STATUS_AMBIGUOUS,
            active_id_socio=None,
            matched_signals=tuple(),
            branch_pin_candidate_count=(
                candidate_counts[
                    SIGNAL_BRANCH_PIN
                ]
            ),
            phone_candidate_count=(
                candidate_counts[
                    SIGNAL_PHONE
                ]
            ),
            email_candidate_count=(
                candidate_counts[
                    SIGNAL_EMAIL
                ]
            ),
        )

    return SocioVencidoCurrentStatus(
        vencido_row_id=vencido_row_id,
        status=STATUS_NOT_FOUND,
        active_id_socio=None,
        matched_signals=tuple(),
        branch_pin_candidate_count=0,
        phone_candidate_count=0,
        email_candidate_count=0,
    )


def _ensure_positive_int(
    value: Any,
    *,
    field_name: str,
) -> int:
    if (
        not isinstance(
            value,
            int,
        )
        or isinstance(
            value,
            bool,
        )
        or value <= 0
    ):
        raise ValueError(
            f"{field_name} debe ser entero positivo."
        )

    return value


def _ensure_date(value: Any, *, field_name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{field_name} debe ser fecha ISO.") from exc
    raise ValueError(f"{field_name} es obligatorio.")


def _normalize_required_id_socio(
    value: Any,
) -> str:
    normalized = str(
        value or ""
    ).strip()

    if not normalized:
        raise SociosVencidosCurrentStatusResolverError(
            "Socios Activos contiene una fila "
            "sin id_socio."
        )

    return normalized


def _normalize_text(
    value: Any,
) -> str | None:
    if value is None:
        return None

    text_value = " ".join(
        str(value)
        .replace("\xa0", " ")
        .strip()
        .split()
    )

    if not text_value:
        return None

    normalized = "".join(
        character
        for character in unicodedata.normalize(
            "NFKD",
            text_value,
        )
        if not unicodedata.combining(
            character
        )
    )

    return " ".join(
        normalized.upper().split()
    )


def normalize_socios_vencidos_branch_key(
    value: Any,
) -> str | None:
    """Normaliza sucursal con las mismas reglas del matcher vigente."""

    return _normalize_text(value)


def _normalize_pin(
    value: Any,
) -> str | None:
    normalized = _normalize_text(
        value
    )

    if not normalized:
        return None

    if re.fullmatch(
        r"\d+(?:\.0+)?",
        normalized,
    ):
        return str(
            int(
                normalized.split(
                    ".",
                    1,
                )[0]
            )
        )

    return normalized


def _normalize_phone(
    value: Any,
) -> str | None:
    if value is None:
        return None

    digits = re.sub(
        r"\D",
        "",
        str(value),
    )

    if len(digits) == 10:
        return digits

    if (
        len(digits) == 12
        and digits.startswith(
            "52"
        )
    ):
        return digits[-10:]

    if (
        len(digits) == 13
        and digits.startswith(
            "521"
        )
    ):
        return digits[-10:]

    return None


def _normalize_email(
    value: Any,
) -> str | None:
    if value is None:
        return None

    normalized = str(
        value
    ).strip().lower()

    if (
        not normalized
        or "@" not in normalized
    ):
        return None

    return normalized
