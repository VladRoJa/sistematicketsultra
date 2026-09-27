from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func

from app.extensions import db
from app.models.attendance import WarehouseAttendanceVisitORM
from app.models.warehouse import (
    SociosActivosSnapshotORM,
    SociosActivosSnapshotRowORM,
    TrackBranchAliasORM,
    TrackBranchCatalogORM,
)
from app.routine_control.pipeline.branch_resolver import (
    GASCA_SOURCE_FAMILY,
)


IDENTITY_EXACT_PIN_ALTA = "EXACT_PIN_ALTA"
IDENTITY_SAME_DAY_PIN = "SAME_DAY_PIN"
IDENTITY_SAME_DAY_BRANCH_PIN = "SAME_DAY_BRANCH_PIN"
IDENTITY_UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class AttendanceIdentityResolution:
    id_socio: str | None
    display_name: str | None
    identity_method: str
    source_snapshot_id: int | None


@dataclass(frozen=True, slots=True)
class _IdentityCandidate:
    id_socio: str
    nombre: str | None
    snapshot_id: int


def resolve_attendance_identity(
    visit: WarehouseAttendanceVisitORM,
    *,
    session: Any | None = None,
) -> AttendanceIdentityResolution:
    active_session = session or db.session
    fallback_name = _source_display_name(visit)

    if (
        str(getattr(visit, "attendance_type", "") or "")
        .strip()
        .upper()
        != "SOCIO"
    ):
        return _unresolved(fallback_name)

    member_pin = _clean_text(
        getattr(visit, "member_pin", None)
    )
    if not member_pin:
        return _unresolved(fallback_name)

    member_since = getattr(
        visit,
        "member_since",
        None,
    )

    if member_since is not None:
        exact_candidates = _load_exact_candidates(
            active_session,
            member_pin=member_pin,
            member_since=member_since,
        )
        exact = _unique_candidate(exact_candidates)
        if exact is not None:
            return _resolved(
                exact,
                method=IDENTITY_EXACT_PIN_ALTA,
                fallback_name=fallback_name,
            )

    business_date = getattr(
        visit,
        "business_date",
        None,
    )
    if business_date is None:
        return _unresolved(fallback_name)

    snapshot_id = _load_same_day_snapshot_id(
        active_session,
        business_date=business_date,
    )
    if snapshot_id is None:
        return _unresolved(fallback_name)

    same_day_candidates = _load_same_day_pin_candidates(
        active_session,
        snapshot_id=snapshot_id,
        member_pin=member_pin,
    )
    same_day = _unique_candidate(
        same_day_candidates
    )
    if same_day is not None:
        return _resolved(
            same_day,
            method=IDENTITY_SAME_DAY_PIN,
            fallback_name=fallback_name,
        )

    sucursal_id = getattr(
        visit,
        "sucursal_id",
        None,
    )
    if (
        not isinstance(sucursal_id, int)
        or isinstance(sucursal_id, bool)
        or sucursal_id <= 0
    ):
        return _unresolved(fallback_name)

    branch_candidates = (
        _load_same_day_branch_pin_candidates(
            active_session,
            snapshot_id=snapshot_id,
            member_pin=member_pin,
            sucursal_id=sucursal_id,
        )
    )
    branch = _unique_candidate(
        branch_candidates
    )
    if branch is not None:
        return _resolved(
            branch,
            method=(
                IDENTITY_SAME_DAY_BRANCH_PIN
            ),
            fallback_name=fallback_name,
        )

    return _unresolved(fallback_name)


def _load_exact_candidates(
    session: Any,
    *,
    member_pin: str,
    member_since: Any,
) -> tuple[_IdentityCandidate, ...]:
    rows = (
        session.query(
            SociosActivosSnapshotRowORM.id_socio,
            SociosActivosSnapshotRowORM.nombre,
            SociosActivosSnapshotORM.id.label(
                "snapshot_id"
            ),
        )
        .join(
            SociosActivosSnapshotORM,
            SociosActivosSnapshotORM.id
            == SociosActivosSnapshotRowORM.snapshot_id,
        )
        .filter(
            SociosActivosSnapshotORM.report_type_key
            == "socios_activos",
            SociosActivosSnapshotORM.snapshot_kind
            == "daily",
            SociosActivosSnapshotORM.is_canonical
            .is_(True),
            SociosActivosSnapshotRowORM.pin
            == member_pin,
            func.date(
                SociosActivosSnapshotRowORM
                .fecha_ingreso_local
            )
            == member_since,
        )
        .order_by(
            SociosActivosSnapshotORM.cutoff_date
            .desc(),
            SociosActivosSnapshotORM.captured_at
            .desc(),
            SociosActivosSnapshotORM.id.desc(),
            SociosActivosSnapshotRowORM.id.desc(),
        )
        .all()
    )
    return tuple(
        _candidate_from_row(row)
        for row in rows
    )


def _load_same_day_snapshot_id(
    session: Any,
    *,
    business_date: Any,
) -> int | None:
    row = (
        session.query(
            SociosActivosSnapshotORM.id
        )
        .filter(
            SociosActivosSnapshotORM.report_type_key
            == "socios_activos",
            SociosActivosSnapshotORM.snapshot_kind
            == "daily",
            SociosActivosSnapshotORM.is_canonical
            .is_(True),
            SociosActivosSnapshotORM.cutoff_date
            == business_date,
        )
        .order_by(
            SociosActivosSnapshotORM.captured_at
            .desc(),
            SociosActivosSnapshotORM.id.desc(),
        )
        .first()
    )
    if row is None:
        return None

    snapshot_id = (
        row[0]
        if isinstance(row, tuple)
        else getattr(row, "id", row)
    )
    try:
        parsed = int(snapshot_id)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _load_same_day_pin_candidates(
    session: Any,
    *,
    snapshot_id: int,
    member_pin: str,
) -> tuple[_IdentityCandidate, ...]:
    rows = (
        session.query(
            SociosActivosSnapshotRowORM.id_socio,
            SociosActivosSnapshotRowORM.nombre,
            SociosActivosSnapshotRowORM.snapshot_id,
        )
        .filter(
            SociosActivosSnapshotRowORM.snapshot_id
            == snapshot_id,
            SociosActivosSnapshotRowORM.pin
            == member_pin,
        )
        .all()
    )
    return tuple(
        _candidate_from_row(row)
        for row in rows
    )


def _load_same_day_branch_pin_candidates(
    session: Any,
    *,
    snapshot_id: int,
    member_pin: str,
    sucursal_id: int,
) -> tuple[_IdentityCandidate, ...]:
    rows = (
        session.query(
            SociosActivosSnapshotRowORM.id_socio,
            SociosActivosSnapshotRowORM.nombre,
            SociosActivosSnapshotRowORM.snapshot_id,
        )
        .join(
            TrackBranchAliasORM,
            (
                TrackBranchAliasORM.raw_branch_name
                == SociosActivosSnapshotRowORM.sucursal_raw
            )
            & (
                TrackBranchAliasORM.source_family
                == GASCA_SOURCE_FAMILY
            )
            & (
                TrackBranchAliasORM.is_active
                .is_(True)
            ),
        )
        .join(
            TrackBranchCatalogORM,
            TrackBranchCatalogORM.sucursal_canon
            == TrackBranchAliasORM.sucursal_canon,
        )
        .filter(
            SociosActivosSnapshotRowORM.snapshot_id
            == snapshot_id,
            SociosActivosSnapshotRowORM.pin
            == member_pin,
            TrackBranchCatalogORM.sucursal_id
            == sucursal_id,
        )
        .all()
    )
    return tuple(
        _candidate_from_row(row)
        for row in rows
    )


def _candidate_from_row(
    row: Any,
) -> _IdentityCandidate:
    return _IdentityCandidate(
        id_socio=str(
            getattr(row, "id_socio", row[0])
        ).strip(),
        nombre=_clean_text(
            getattr(row, "nombre", row[1])
        ),
        snapshot_id=int(
            getattr(row, "snapshot_id", row[2])
        ),
    )


def _unique_candidate(
    candidates: tuple[_IdentityCandidate, ...],
) -> _IdentityCandidate | None:
    by_id: dict[str, _IdentityCandidate] = {}

    for candidate in candidates:
        normalized_id = _clean_text(
            candidate.id_socio
        )
        if not normalized_id:
            continue
        if normalized_id not in by_id:
            by_id[normalized_id] = candidate

    if len(by_id) != 1:
        return None

    return next(iter(by_id.values()))


def _resolved(
    candidate: _IdentityCandidate,
    *,
    method: str,
    fallback_name: str | None,
) -> AttendanceIdentityResolution:
    return AttendanceIdentityResolution(
        id_socio=candidate.id_socio,
        display_name=(
            _clean_text(candidate.nombre)
            or fallback_name
        ),
        identity_method=method,
        source_snapshot_id=(
            candidate.snapshot_id
        ),
    )


def _unresolved(
    fallback_name: str | None,
) -> AttendanceIdentityResolution:
    return AttendanceIdentityResolution(
        id_socio=None,
        display_name=fallback_name,
        identity_method=IDENTITY_UNRESOLVED,
        source_snapshot_id=None,
    )


def _source_display_name(
    visit: WarehouseAttendanceVisitORM,
) -> str | None:
    parts = [
        _clean_text(
            getattr(
                visit,
                "source_first_name",
                None,
            )
        ),
        _clean_text(
            getattr(
                visit,
                "source_last_name",
                None,
            )
        ),
    ]
    value = " ".join(
        part for part in parts if part
    ).strip()
    return value or None


def _clean_text(
    value: Any,
) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
