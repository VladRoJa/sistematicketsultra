from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, tuple_

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


def resolve_attendance_identities(
    visits: list[WarehouseAttendanceVisitORM]
    | tuple[WarehouseAttendanceVisitORM, ...],
    *,
    session: Any | None = None,
    chunk_size: int = 1000,
) -> dict[int, AttendanceIdentityResolution]:
    active_session = session or db.session
    safe_chunk_size = max(1, int(chunk_size))

    resolutions: dict[
        int,
        AttendanceIdentityResolution,
    ] = {}
    eligible: list[
        WarehouseAttendanceVisitORM
    ] = []

    for visit in visits:
        visit_id = _visit_id(visit)
        fallback_name = _source_display_name(
            visit
        )

        if visit_id is None:
            continue

        resolutions[visit_id] = _unresolved(
            fallback_name
        )

        if (
            str(
                getattr(
                    visit,
                    "attendance_type",
                    "",
                )
                or ""
            )
            .strip()
            .upper()
            != "SOCIO"
        ):
            continue

        if not _clean_text(
            getattr(
                visit,
                "member_pin",
                None,
            )
        ):
            continue

        eligible.append(visit)

    unresolved_ids = {
        _visit_id(visit)
        for visit in eligible
        if _visit_id(visit) is not None
    }

    exact_keys = {
        (
            _clean_text(visit.member_pin),
            visit.member_since,
        )
        for visit in eligible
        if (
            _visit_id(visit) in unresolved_ids
            and visit.member_since is not None
            and _clean_text(
                visit.member_pin
            )
        )
    }
    exact_candidates = (
        _load_exact_candidates_batch(
            active_session,
            keys=exact_keys,
            chunk_size=safe_chunk_size,
        )
    )

    for visit in eligible:
        visit_id = _visit_id(visit)
        if (
            visit_id is None
            or visit_id not in unresolved_ids
            or visit.member_since is None
        ):
            continue

        key = (
            _clean_text(visit.member_pin),
            visit.member_since,
        )
        candidate = _unique_candidate(
            exact_candidates.get(
                key,
                (),
            )
        )
        if candidate is None:
            continue

        resolutions[visit_id] = _resolved(
            candidate,
            method=IDENTITY_EXACT_PIN_ALTA,
            fallback_name=_source_display_name(
                visit
            ),
        )
        unresolved_ids.discard(visit_id)

    unresolved_visits = [
        visit
        for visit in eligible
        if _visit_id(visit) in unresolved_ids
    ]
    dates = {
        visit.business_date
        for visit in unresolved_visits
        if visit.business_date is not None
    }
    snapshot_by_date = (
        _load_same_day_snapshot_ids_batch(
            active_session,
            business_dates=dates,
        )
    )

    same_day_keys = {
        (
            snapshot_by_date[
                visit.business_date
            ],
            _clean_text(visit.member_pin),
        )
        for visit in unresolved_visits
        if (
            visit.business_date
            in snapshot_by_date
            and _clean_text(
                visit.member_pin
            )
        )
    }
    same_day_candidates = (
        _load_same_day_pin_candidates_batch(
            active_session,
            keys=same_day_keys,
            chunk_size=safe_chunk_size,
        )
    )

    for visit in unresolved_visits:
        visit_id = _visit_id(visit)
        if (
            visit_id is None
            or visit_id not in unresolved_ids
            or visit.business_date
            not in snapshot_by_date
        ):
            continue

        key = (
            snapshot_by_date[
                visit.business_date
            ],
            _clean_text(visit.member_pin),
        )
        candidate = _unique_candidate(
            same_day_candidates.get(
                key,
                (),
            )
        )
        if candidate is None:
            continue

        resolutions[visit_id] = _resolved(
            candidate,
            method=IDENTITY_SAME_DAY_PIN,
            fallback_name=_source_display_name(
                visit
            ),
        )
        unresolved_ids.discard(visit_id)

    branch_visits = [
        visit
        for visit in eligible
        if (
            _visit_id(visit) in unresolved_ids
            and visit.business_date
            in snapshot_by_date
            and _valid_branch_id(
                getattr(
                    visit,
                    "sucursal_id",
                    None,
                )
            )
        )
    ]

    branch_keys = {
        (
            snapshot_by_date[
                visit.business_date
            ],
            _clean_text(visit.member_pin),
            int(visit.sucursal_id),
        )
        for visit in branch_visits
        if _clean_text(
            visit.member_pin
        )
    }
    branch_candidates = (
        _load_same_day_branch_pin_candidates_batch(
            active_session,
            keys=branch_keys,
            chunk_size=safe_chunk_size,
        )
    )

    for visit in branch_visits:
        visit_id = _visit_id(visit)
        if (
            visit_id is None
            or visit_id not in unresolved_ids
        ):
            continue

        key = (
            snapshot_by_date[
                visit.business_date
            ],
            _clean_text(visit.member_pin),
            int(visit.sucursal_id),
        )
        candidate = _unique_candidate(
            branch_candidates.get(
                key,
                (),
            )
        )
        if candidate is None:
            continue

        resolutions[visit_id] = _resolved(
            candidate,
            method=(
                IDENTITY_SAME_DAY_BRANCH_PIN
            ),
            fallback_name=_source_display_name(
                visit
            ),
        )
        unresolved_ids.discard(visit_id)

    return resolutions


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


def _load_exact_candidates_batch(
    session: Any,
    *,
    keys: set[tuple[str | None, Any]],
    chunk_size: int,
) -> dict[
    tuple[str | None, Any],
    tuple[_IdentityCandidate, ...],
]:
    result: dict[
        tuple[str | None, Any],
        list[_IdentityCandidate],
    ] = {}

    normalized_keys = [
        (pin, member_since)
        for pin, member_since in keys
        if pin and member_since is not None
    ]

    member_since_expr = func.date(
        SociosActivosSnapshotRowORM
        .fecha_ingreso_local
    )

    for chunk in _chunked(
        normalized_keys,
        chunk_size,
    ):
        ranked = (
            session.query(
                SociosActivosSnapshotRowORM.pin.label(
                    "pin"
                ),
                member_since_expr.label(
                    "member_since"
                ),
                SociosActivosSnapshotRowORM.id_socio.label(
                    "id_socio"
                ),
                SociosActivosSnapshotRowORM.nombre.label(
                    "nombre"
                ),
                SociosActivosSnapshotORM.id.label(
                    "snapshot_id"
                ),
                func.row_number()
                .over(
                    partition_by=(
                        SociosActivosSnapshotRowORM.pin,
                        member_since_expr,
                        SociosActivosSnapshotRowORM.id_socio,
                    ),
                    order_by=(
                        SociosActivosSnapshotORM.cutoff_date
                        .desc(),
                        SociosActivosSnapshotORM.captured_at
                        .desc(),
                        SociosActivosSnapshotORM.id.desc(),
                        SociosActivosSnapshotRowORM.id.desc(),
                    ),
                )
                .label("row_number"),
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
                tuple_(
                    SociosActivosSnapshotRowORM.pin,
                    member_since_expr,
                ).in_(chunk),
            )
            .subquery()
        )

        rows = (
            session.query(
                ranked.c.pin,
                ranked.c.member_since,
                ranked.c.id_socio,
                ranked.c.nombre,
                ranked.c.snapshot_id,
            )
            .filter(
                ranked.c.row_number == 1
            )
            .all()
        )

        for row in rows:
            key = (
                _clean_text(
                    _row_value(
                        row,
                        "pin",
                        0,
                    )
                ),
                _row_value(
                    row,
                    "member_since",
                    1,
                ),
            )
            result.setdefault(
                key,
                [],
            ).append(
                _IdentityCandidate(
                    id_socio=str(
                        _row_value(
                            row,
                            "id_socio",
                            2,
                        )
                    ).strip(),
                    nombre=_clean_text(
                        _row_value(
                            row,
                            "nombre",
                            3,
                        )
                    ),
                    snapshot_id=int(
                        _row_value(
                            row,
                            "snapshot_id",
                            4,
                        )
                    ),
                )
            )

    return {
        key: tuple(candidates)
        for key, candidates
        in result.items()
    }

def _load_same_day_snapshot_ids_batch(
    session: Any,
    *,
    business_dates: set[Any],
) -> dict[Any, int]:
    if not business_dates:
        return {}

    rows = (
        session.query(
            SociosActivosSnapshotORM.cutoff_date,
            SociosActivosSnapshotORM.id,
        )
        .filter(
            SociosActivosSnapshotORM.report_type_key
            == "socios_activos",
            SociosActivosSnapshotORM.snapshot_kind
            == "daily",
            SociosActivosSnapshotORM.is_canonical
            .is_(True),
            SociosActivosSnapshotORM.cutoff_date
            .in_(business_dates),
        )
        .order_by(
            SociosActivosSnapshotORM.cutoff_date,
            SociosActivosSnapshotORM.captured_at
            .desc(),
            SociosActivosSnapshotORM.id.desc(),
        )
        .all()
    )

    result: dict[Any, int] = {}
    for row in rows:
        business_date = _row_value(
            row,
            "cutoff_date",
            0,
        )
        if business_date in result:
            continue
        snapshot_id = int(
            _row_value(
                row,
                "id",
                1,
            )
        )
        if snapshot_id > 0:
            result[business_date] = snapshot_id

    return result


def _load_same_day_pin_candidates_batch(
    session: Any,
    *,
    keys: set[tuple[int, str | None]],
    chunk_size: int,
) -> dict[
    tuple[int, str | None],
    tuple[_IdentityCandidate, ...],
]:
    result: dict[
        tuple[int, str | None],
        list[_IdentityCandidate],
    ] = {}

    normalized_keys = [
        (snapshot_id, pin)
        for snapshot_id, pin in keys
        if snapshot_id > 0 and pin
    ]

    for chunk in _chunked(
        normalized_keys,
        chunk_size,
    ):
        rows = (
            session.query(
                SociosActivosSnapshotRowORM.snapshot_id,
                SociosActivosSnapshotRowORM.pin,
                SociosActivosSnapshotRowORM.id_socio,
                SociosActivosSnapshotRowORM.nombre,
            )
            .filter(
                tuple_(
                    SociosActivosSnapshotRowORM.snapshot_id,
                    SociosActivosSnapshotRowORM.pin,
                ).in_(chunk)
            )
            .all()
        )

        for row in rows:
            key = (
                int(
                    _row_value(
                        row,
                        "snapshot_id",
                        0,
                    )
                ),
                _clean_text(
                    _row_value(
                        row,
                        "pin",
                        1,
                    )
                ),
            )
            result.setdefault(
                key,
                [],
            ).append(
                _IdentityCandidate(
                    id_socio=str(
                        _row_value(
                            row,
                            "id_socio",
                            2,
                        )
                    ).strip(),
                    nombre=_clean_text(
                        _row_value(
                            row,
                            "nombre",
                            3,
                        )
                    ),
                    snapshot_id=key[0],
                )
            )

    return {
        key: tuple(candidates)
        for key, candidates
        in result.items()
    }


def _load_same_day_branch_pin_candidates_batch(
    session: Any,
    *,
    keys: set[
        tuple[int, str | None, int]
    ],
    chunk_size: int,
) -> dict[
    tuple[int, str | None, int],
    tuple[_IdentityCandidate, ...],
]:
    result: dict[
        tuple[int, str | None, int],
        list[_IdentityCandidate],
    ] = {}

    normalized_keys = [
        (
            snapshot_id,
            pin,
            sucursal_id,
        )
        for (
            snapshot_id,
            pin,
            sucursal_id,
        ) in keys
        if (
            snapshot_id > 0
            and pin
            and sucursal_id > 0
        )
    ]

    for chunk in _chunked(
        normalized_keys,
        chunk_size,
    ):
        rows = (
            session.query(
                SociosActivosSnapshotRowORM.snapshot_id,
                SociosActivosSnapshotRowORM.pin,
                TrackBranchCatalogORM.sucursal_id,
                SociosActivosSnapshotRowORM.id_socio,
                SociosActivosSnapshotRowORM.nombre,
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
                tuple_(
                    SociosActivosSnapshotRowORM.snapshot_id,
                    SociosActivosSnapshotRowORM.pin,
                    TrackBranchCatalogORM.sucursal_id,
                ).in_(chunk)
            )
            .all()
        )

        for row in rows:
            key = (
                int(
                    _row_value(
                        row,
                        "snapshot_id",
                        0,
                    )
                ),
                _clean_text(
                    _row_value(
                        row,
                        "pin",
                        1,
                    )
                ),
                int(
                    _row_value(
                        row,
                        "sucursal_id",
                        2,
                    )
                ),
            )
            result.setdefault(
                key,
                [],
            ).append(
                _IdentityCandidate(
                    id_socio=str(
                        _row_value(
                            row,
                            "id_socio",
                            3,
                        )
                    ).strip(),
                    nombre=_clean_text(
                        _row_value(
                            row,
                            "nombre",
                            4,
                        )
                    ),
                    snapshot_id=key[0],
                )
            )

    return {
        key: tuple(candidates)
        for key, candidates
        in result.items()
    }


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

    snapshot_id = _row_value(
        row,
        "id",
        0,
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
            _row_value(
                row,
                "id_socio",
                0,
            )
        ).strip(),
        nombre=_clean_text(
            _row_value(
                row,
                "nombre",
                1,
            )
        ),
        snapshot_id=int(
            _row_value(
                row,
                "snapshot_id",
                2,
            )
        ),
    )


def _row_value(
    row: Any,
    attribute: str,
    index: int,
) -> Any:
    if hasattr(row, attribute):
        return getattr(row, attribute)
    return row[index]


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


def _visit_id(
    visit: WarehouseAttendanceVisitORM,
) -> int | None:
    value = getattr(
        visit,
        "id",
        None,
    )
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _valid_branch_id(
    value: Any,
) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value > 0
    )


def _chunked(
    values: list[Any],
    size: int,
) -> list[list[Any]]:
    return [
        values[index : index + size]
        for index in range(
            0,
            len(values),
            size,
        )
    ]


def _clean_text(
    value: Any,
) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
