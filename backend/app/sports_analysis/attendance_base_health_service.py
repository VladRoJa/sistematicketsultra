from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from math import ceil
from statistics import median
from types import SimpleNamespace
from typing import Any

from sqlalchemy import func, or_, tuple_

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

from .attendance_access import (
    SportsAnalysisScope,
    scoped_branch_catalog,
)
from .attendance_identity_service import (
    resolve_attendance_identities,
)
from .attendance_query_service import (
    SportsAnalysisValidationError,
    _effective_branch_ids,
    _validate_date_range,
)


BASE_HEALTH_STATUS_WITH_VISIT = "WITH_VISIT"
BASE_HEALTH_STATUS_WITHOUT_VISIT = "WITHOUT_VISIT"
BASE_HEALTH_MEMBER_STATUSES = {
    BASE_HEALTH_STATUS_WITH_VISIT,
    BASE_HEALTH_STATUS_WITHOUT_VISIT,
}
DEFAULT_MEMBER_PAGE_SIZE = 50
MAX_MEMBER_PAGE_SIZE = 200
IDENTITY_BATCH_SIZE = 2000


@dataclass(frozen=True, slots=True)
class _EligibleMember:
    id_socio: str
    pin: str
    name: str | None
    branch_id: int
    branch_name: str
    member_since: date | None
    expiration_date: date
    snapshot_date: date


@dataclass(frozen=True, slots=True)
class _MemberVisitStats:
    visit_count: int
    first_visit_date: date
    last_visit_date: date


@dataclass(frozen=True, slots=True)
class _BaseHealthState:
    eligible_members: dict[str, _EligibleMember]
    visited_member_ids: frozenset[str]
    snapshot_dates: tuple[date, ...]
    total_visits_checked: int
    resolved_visits: int
    member_visit_stats: dict[
        str,
        _MemberVisitStats,
    ] = field(default_factory=dict)
    last_known_visit_by_member: dict[
        str,
        date,
    ] = field(default_factory=dict)


def attendance_base_health(
    scope: SportsAnalysisScope,
    *,
    date_from: date,
    date_to: date,
    branch_id: int | None,
    region_key: str | None,
) -> dict[str, Any]:
    state, effective_branch_ids = _build_state(
        scope,
        date_from=date_from,
        date_to=date_to,
        branch_id=branch_id,
        region_key=region_key,
    )

    eligible_ids = set(state.eligible_members)
    with_visit_ids = (
        eligible_ids
        & set(state.visited_member_ids)
    )
    eligible_count = len(eligible_ids)
    with_visit_count = len(with_visit_ids)
    without_visit_count = (
        eligible_count - with_visit_count
    )
    utilization_pct = (
        round(
            with_visit_count
            * 100
            / eligible_count,
            1,
        )
        if eligible_count
        else 0.0
    )
    without_visit_pct = (
        round(
            without_visit_count
            * 100
            / eligible_count,
            1,
        )
        if eligible_count
        else 0.0
    )
    identity_coverage_pct = (
        round(
            state.resolved_visits
            * 100
            / state.total_visits_checked,
            1,
        )
        if state.total_visits_checked
        else 0.0
    )
    frequency = _frequency_metrics(
        state,
        date_from=date_from,
        date_to=date_to,
    )
    recency = _recency_metrics(
        state,
        date_to=date_to,
    )

    return {
        "scope": {
            "role": scope.role,
            "is_global": scope.is_global,
            "allowed_branch_ids": list(
                scope.allowed_branch_ids
            ),
        },
        "filters": {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "branch_id": branch_id,
            "region_key": region_key,
            "attendance_type": "SOCIO",
        },
        "summary": {
            "eligible_members": eligible_count,
            "members_with_visit": with_visit_count,
            "members_without_visit": (
                without_visit_count
            ),
            "utilization_pct": utilization_pct,
            "without_visit_pct": (
                without_visit_pct
            ),
            "frequency_avg_per_week": (
                frequency["average_per_week"]
            ),
            "frequency_median_per_week": (
                frequency["median_per_week"]
            ),
            "members_14_plus_days_without_visit": (
                recency[
                    "members_14_plus_days_without_visit"
                ]
            ),
        },
        "frequency_distribution": (
            frequency["distribution"]
        ),
        "recency_distribution": (
            recency["distribution"]
        ),
        "source": {
            "available": bool(
                state.snapshot_dates
            ),
            "snapshot_count": len(
                state.snapshot_dates
            ),
            "first_snapshot_date": (
                state.snapshot_dates[0].isoformat()
                if state.snapshot_dates
                else None
            ),
            "last_snapshot_date": (
                state.snapshot_dates[-1].isoformat()
                if state.snapshot_dates
                else None
            ),
            "identity_coverage_pct": (
                identity_coverage_pct
            ),
            "visits_checked": (
                state.total_visits_checked
            ),
            "visits_resolved": (
                state.resolved_visits
            ),
            "effective_branch_ids": list(
                effective_branch_ids
            ),
        },
    }


def attendance_base_health_members(
    scope: SportsAnalysisScope,
    *,
    date_from: date,
    date_to: date,
    branch_id: int | None,
    region_key: str | None,
    status: str,
    page: object = 1,
    page_size: object = DEFAULT_MEMBER_PAGE_SIZE,
) -> dict[str, Any]:
    normalized_status = str(
        status or ""
    ).strip().upper()
    if normalized_status not in (
        BASE_HEALTH_MEMBER_STATUSES
    ):
        raise SportsAnalysisValidationError(
            "status debe ser WITH_VISIT "
            "o WITHOUT_VISIT."
        )

    safe_page = _positive_int(
        page,
        field_name="page",
        default=1,
    )
    safe_page_size = min(
        _positive_int(
            page_size,
            field_name="page_size",
            default=DEFAULT_MEMBER_PAGE_SIZE,
        ),
        MAX_MEMBER_PAGE_SIZE,
    )

    state, _ = _build_state(
        scope,
        date_from=date_from,
        date_to=date_to,
        branch_id=branch_id,
        region_key=region_key,
    )

    visited = set(state.visited_member_ids)
    want_visit = (
        normalized_status
        == BASE_HEALTH_STATUS_WITH_VISIT
    )

    members = [
        member
        for member
        in state.eligible_members.values()
        if (
            (member.id_socio in visited)
            == want_visit
        )
    ]
    members.sort(
        key=lambda member: (
            member.branch_name.casefold(),
            (member.name or "").casefold(),
            member.id_socio,
        )
    )

    count = len(members)
    total_pages = max(
        1,
        ceil(count / safe_page_size),
    )
    safe_page = min(
        safe_page,
        total_pages,
    )
    start = (
        (safe_page - 1)
        * safe_page_size
    )
    page_rows = members[
        start:start + safe_page_size
    ]

    return {
        "status": normalized_status,
        "title": (
            "Socios que usaron el gimnasio"
            if want_visit
            else "Socios sin visitas en el periodo"
        ),
        "count": count,
        "page": safe_page,
        "page_size": safe_page_size,
        "total_pages": total_pages,
        "rows": [
            _serialize_member(
                member,
                has_visit=want_visit,
            )
            for member in page_rows
        ],
    }


def _build_state(
    scope: SportsAnalysisScope,
    *,
    date_from: date,
    date_to: date,
    branch_id: int | None,
    region_key: str | None,
) -> tuple[_BaseHealthState, tuple[int, ...]]:
    _validate_date_range(
        date_from,
        date_to,
    )

    branches = scoped_branch_catalog(scope)
    effective_branch_ids = (
        _effective_branch_ids(
            branches,
            branch_id=branch_id,
            region_key=region_key,
        )
    )

    (
        eligible_members,
        snapshot_dates,
    ) = _load_eligible_members(
        effective_branch_ids,
        date_from=date_from,
        date_to=date_to,
    )

    if not eligible_members:
        return (
            _BaseHealthState(
                eligible_members={},
                visited_member_ids=frozenset(),
                snapshot_dates=snapshot_dates,
                total_visits_checked=0,
                resolved_visits=0,
                member_visit_stats={},
                last_known_visit_by_member={},
            ),
            effective_branch_ids,
        )

    (
        member_visit_stats,
        total_visits_checked,
        resolved_visits,
    ) = _load_member_visit_stats(
        tuple(scope.allowed_branch_ids),
        date_from=date_from,
        date_to=date_to,
    )

    last_known_visit_by_member = {
        id_socio: stats.last_visit_date
        for id_socio, stats
        in member_visit_stats.items()
    }
    historical_last_visits = (
        _load_historical_last_visits(
            eligible_members,
            member_visit_stats,
            date_before=date_from,
        )
    )
    last_known_visit_by_member.update(
        historical_last_visits
    )

    return (
        _BaseHealthState(
            eligible_members=eligible_members,
            visited_member_ids=frozenset(
                member_visit_stats
            ),
            snapshot_dates=snapshot_dates,
            total_visits_checked=(
                total_visits_checked
            ),
            resolved_visits=resolved_visits,
            member_visit_stats=member_visit_stats,
            last_known_visit_by_member=(
                last_known_visit_by_member
            ),
        ),
        effective_branch_ids,
    )


def _load_eligible_members(
    branch_ids: tuple[int, ...],
    *,
    date_from: date,
    date_to: date,
) -> tuple[
    dict[str, _EligibleMember],
    tuple[date, ...],
]:
    if not branch_ids:
        return {}, ()

    snapshot_rows = (
        db.session.query(
            SociosActivosSnapshotORM.id,
            SociosActivosSnapshotORM.cutoff_date,
        )
        .filter(
            SociosActivosSnapshotORM.report_type_key
            == "socios_activos",
            SociosActivosSnapshotORM.snapshot_kind
            == "daily",
            SociosActivosSnapshotORM.is_canonical
            .is_(True),
            SociosActivosSnapshotORM.cutoff_date
            .between(
                date_from,
                date_to,
            ),
        )
        .order_by(
            SociosActivosSnapshotORM.cutoff_date,
            SociosActivosSnapshotORM.captured_at,
            SociosActivosSnapshotORM.id,
        )
        .all()
    )

    baseline = (
        db.session.query(
            SociosActivosSnapshotORM.id,
            SociosActivosSnapshotORM.cutoff_date,
        )
        .filter(
            SociosActivosSnapshotORM.report_type_key
            == "socios_activos",
            SociosActivosSnapshotORM.snapshot_kind
            == "daily",
            SociosActivosSnapshotORM.is_canonical
            .is_(True),
            SociosActivosSnapshotORM.cutoff_date
            <= date_from,
        )
        .order_by(
            SociosActivosSnapshotORM.cutoff_date
            .desc(),
            SociosActivosSnapshotORM.captured_at
            .desc(),
            SociosActivosSnapshotORM.id.desc(),
        )
        .first()
    )

    snapshots: dict[int, date] = {}
    if baseline is not None:
        snapshots[
            int(_row_value(baseline, "id", 0))
        ] = _row_value(
            baseline,
            "cutoff_date",
            1,
        )

    for row in snapshot_rows:
        snapshots[
            int(_row_value(row, "id", 0))
        ] = _row_value(
            row,
            "cutoff_date",
            1,
        )

    if not snapshots:
        return {}, ()

    rows = (
        db.session.query(
            SociosActivosSnapshotRowORM.id_socio,
            SociosActivosSnapshotRowORM.pin,
            SociosActivosSnapshotRowORM.nombre,
            SociosActivosSnapshotRowORM
            .fecha_ingreso_local,
            SociosActivosSnapshotORM.cutoff_date,
            TrackBranchCatalogORM.sucursal_id,
            TrackBranchCatalogORM.track_label,
            SociosActivosSnapshotRowORM
            .fecha_vencimiento_date,
        )
        .join(
            SociosActivosSnapshotORM,
            SociosActivosSnapshotORM.id
            == SociosActivosSnapshotRowORM
            .snapshot_id,
        )
        .join(
            TrackBranchAliasORM,
            (
                TrackBranchAliasORM.raw_branch_name
                == SociosActivosSnapshotRowORM
                .sucursal_raw
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
            .in_(tuple(snapshots)),
            TrackBranchCatalogORM.sucursal_id
            .in_(branch_ids),
            SociosActivosSnapshotRowORM
            .fecha_vencimiento_date
            >= date_from,
            or_(
                SociosActivosSnapshotRowORM
                .fecha_ingreso_local.is_(None),
                func.date(
                    SociosActivosSnapshotRowORM
                    .fecha_ingreso_local
                )
                <= date_to,
            ),
        )
        .distinct(
            SociosActivosSnapshotRowORM.id_socio
        )
        .order_by(
            SociosActivosSnapshotRowORM.id_socio,
            SociosActivosSnapshotORM.cutoff_date.desc(),
            SociosActivosSnapshotORM.captured_at.desc(),
            SociosActivosSnapshotORM.id.desc(),
            SociosActivosSnapshotRowORM.id.desc(),
        )
        .all()
    )

    members: dict[str, _EligibleMember] = {}
    for row in rows:
        id_socio = _clean_text(
            _row_value(
                row,
                "id_socio",
                0,
            )
        )
        pin = _clean_text(
            _row_value(
                row,
                "pin",
                1,
            )
        )
        if not id_socio or not pin:
            continue

        ingreso = _row_value(
            row,
            "fecha_ingreso_local",
            3,
        )
        member_since = (
            ingreso.date()
            if ingreso is not None
            else None
        )
        branch_id = int(
            _row_value(
                row,
                "sucursal_id",
                5,
            )
        )
        snapshot_date = _row_value(
            row,
            "cutoff_date",
            4,
        )

        members[id_socio] = (
            _EligibleMember(
                id_socio=id_socio,
                pin=pin,
                name=_clean_text(
                    _row_value(
                        row,
                        "nombre",
                        2,
                    )
                ),
                branch_id=branch_id,
                branch_name=(
                    _clean_text(
                        _row_value(
                            row,
                            "track_label",
                            6,
                        )
                    )
                    or str(branch_id)
                ),
                member_since=member_since,
                expiration_date=_row_value(
                    row,
                    "fecha_vencimiento_date",
                    7,
                ),
                snapshot_date=snapshot_date,
            )
        )

    snapshot_dates = tuple(
        sorted(set(snapshots.values()))
    )
    return members, snapshot_dates


def _load_member_visit_stats(
    branch_ids: tuple[int, ...],
    *,
    date_from: date,
    date_to: date,
) -> tuple[
    dict[str, _MemberVisitStats],
    int,
    int,
]:
    if not branch_ids:
        return {}, 0, 0

    visit_count = func.count(
        WarehouseAttendanceVisitORM.id
    ).label("visit_count")

    rows = (
        db.session.query(
            WarehouseAttendanceVisitORM.member_pin,
            WarehouseAttendanceVisitORM.member_since,
            WarehouseAttendanceVisitORM.business_date,
            WarehouseAttendanceVisitORM.sucursal_id,
            WarehouseAttendanceVisitORM
            .source_first_name,
            WarehouseAttendanceVisitORM
            .source_last_name,
            visit_count,
        )
        .filter(
            WarehouseAttendanceVisitORM.sucursal_id
            .in_(branch_ids),
            WarehouseAttendanceVisitORM.business_date
            .between(
                date_from,
                date_to,
            ),
            WarehouseAttendanceVisitORM.attendance_type
            == "SOCIO",
            WarehouseAttendanceVisitORM.member_pin
            .isnot(None),
        )
        .group_by(
            WarehouseAttendanceVisitORM.member_pin,
            WarehouseAttendanceVisitORM.member_since,
            WarehouseAttendanceVisitORM.business_date,
            WarehouseAttendanceVisitORM.sucursal_id,
            WarehouseAttendanceVisitORM
            .source_first_name,
            WarehouseAttendanceVisitORM
            .source_last_name,
        )
        .all()
    )

    exact_keys = (
        db.session.query(
            WarehouseAttendanceVisitORM.member_pin.label(
                "pin"
            ),
            WarehouseAttendanceVisitORM.member_since.label(
                "member_since"
            ),
        )
        .filter(
            WarehouseAttendanceVisitORM.sucursal_id
            .in_(branch_ids),
            WarehouseAttendanceVisitORM.business_date
            .between(
                date_from,
                date_to,
            ),
            WarehouseAttendanceVisitORM.attendance_type
            == "SOCIO",
            WarehouseAttendanceVisitORM.member_pin
            .isnot(None),
            WarehouseAttendanceVisitORM.member_since
            .isnot(None),
        )
        .distinct()
        .subquery()
    )

    exact_rows = (
        db.session.query(
            exact_keys.c.pin,
            exact_keys.c.member_since,
            func.count(
                func.distinct(
                    SociosActivosSnapshotRowORM.id_socio
                )
            ).label("candidate_count"),
            func.min(
                SociosActivosSnapshotRowORM.id_socio
            ).label("id_socio"),
        )
        .join(
            SociosActivosSnapshotRowORM,
            (
                SociosActivosSnapshotRowORM.pin
                == exact_keys.c.pin
            )
            & (
                func.date(
                    SociosActivosSnapshotRowORM
                    .fecha_ingreso_local
                )
                == exact_keys.c.member_since
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
        )
        .group_by(
            exact_keys.c.pin,
            exact_keys.c.member_since,
        )
        .all()
    )

    exact_map = {
        (
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
        ): str(
            _row_value(
                row,
                "id_socio",
                3,
            )
        ).strip()
        for row in exact_rows
        if int(
            _row_value(
                row,
                "candidate_count",
                2,
            )
            or 0
        ) == 1
        and _row_value(
            row,
            "id_socio",
            3,
        )
    }

    member_visit_stats: dict[
        str,
        _MemberVisitStats,
    ] = {}
    total_visits = 0
    resolved_visits = 0
    fallback_probes = []
    fallback_counts: dict[int, int] = {}

    for index, row in enumerate(
        rows,
        start=1,
    ):
        count = int(
            _row_value(
                row,
                "visit_count",
                6,
            )
            or 0
        )
        total_visits += count
        business_date = _row_value(
            row,
            "business_date",
            2,
        )

        key = (
            _clean_text(
                _row_value(
                    row,
                    "member_pin",
                    0,
                )
            ),
            _row_value(
                row,
                "member_since",
                1,
            ),
        )
        exact_id = exact_map.get(key)

        if exact_id:
            _record_member_visits(
                member_visit_stats,
                id_socio=exact_id,
                visit_count=count,
                business_date=business_date,
            )
            resolved_visits += count
            continue

        fallback_counts[index] = count
        fallback_probes.append(
            SimpleNamespace(
                id=index,
                attendance_type="SOCIO",
                member_pin=_row_value(
                    row,
                    "member_pin",
                    0,
                ),
                member_since=_row_value(
                    row,
                    "member_since",
                    1,
                ),
                business_date=business_date,
                sucursal_id=_row_value(
                    row,
                    "sucursal_id",
                    3,
                ),
                source_first_name=_row_value(
                    row,
                    "source_first_name",
                    4,
                ),
                source_last_name=_row_value(
                    row,
                    "source_last_name",
                    5,
                ),
            )
        )

    if fallback_probes:
        resolutions = resolve_attendance_identities(
            fallback_probes,
            session=db.session,
            chunk_size=IDENTITY_BATCH_SIZE,
        )

        for probe in fallback_probes:
            resolution = resolutions.get(
                int(probe.id)
            )
            if (
                resolution is None
                or not resolution.id_socio
            ):
                continue

            count = fallback_counts.get(
                int(probe.id),
                0,
            )
            _record_member_visits(
                member_visit_stats,
                id_socio=str(
                    resolution.id_socio
                ).strip(),
                visit_count=count,
                business_date=probe.business_date,
            )
            resolved_visits += count

    return (
        member_visit_stats,
        total_visits,
        resolved_visits,
    )


def _record_member_visits(
    stats: dict[str, _MemberVisitStats],
    *,
    id_socio: str,
    visit_count: int,
    business_date: date,
) -> None:
    current = stats.get(id_socio)
    if current is None:
        stats[id_socio] = _MemberVisitStats(
            visit_count=visit_count,
            first_visit_date=business_date,
            last_visit_date=business_date,
        )
        return

    stats[id_socio] = _MemberVisitStats(
        visit_count=(
            current.visit_count + visit_count
        ),
        first_visit_date=min(
            current.first_visit_date,
            business_date,
        ),
        last_visit_date=max(
            current.last_visit_date,
            business_date,
        ),
    )

def _load_historical_last_visits(
    eligible_members: dict[
        str,
        _EligibleMember,
    ],
    member_visit_stats: dict[
        str,
        _MemberVisitStats,
    ],
    *,
    date_before: date,
) -> dict[str, date]:
    candidates = [
        member
        for member in eligible_members.values()
        if (
            member.id_socio
            not in member_visit_stats
            and member.member_since is not None
        )
    ]
    if not candidates:
        return {}

    requested_keys = {
        (
            member.pin,
            member.member_since,
        )
        for member in candidates
    }

    exact_map: dict[
        tuple[str, date],
        str,
    ] = {}

    keys_list = list(requested_keys)
    for start in range(
        0,
        len(keys_list),
        IDENTITY_BATCH_SIZE,
    ):
        chunk = keys_list[
            start : start + IDENTITY_BATCH_SIZE
        ]

        rows = (
            db.session.query(
                SociosActivosSnapshotRowORM.pin,
                func.date(
                    SociosActivosSnapshotRowORM
                    .fecha_ingreso_local
                ).label("member_since"),
                func.count(
                    func.distinct(
                        SociosActivosSnapshotRowORM.id_socio
                    )
                ).label("candidate_count"),
                func.min(
                    SociosActivosSnapshotRowORM.id_socio
                ).label("id_socio"),
            )
            .join(
                SociosActivosSnapshotORM,
                SociosActivosSnapshotORM.id
                == SociosActivosSnapshotRowORM
                .snapshot_id,
            )
            .filter(
                tuple_(
                    SociosActivosSnapshotRowORM.pin,
                    func.date(
                        SociosActivosSnapshotRowORM
                        .fecha_ingreso_local
                    ),
                ).in_(chunk),
                SociosActivosSnapshotORM.report_type_key
                == "socios_activos",
                SociosActivosSnapshotORM.snapshot_kind
                == "daily",
                SociosActivosSnapshotORM.is_canonical
                .is_(True),
            )
            .group_by(
                SociosActivosSnapshotRowORM.pin,
                func.date(
                    SociosActivosSnapshotRowORM
                    .fecha_ingreso_local
                ),
            )
            .all()
        )

        for row in rows:
            candidate_count = int(
                _row_value(
                    row,
                    "candidate_count",
                    2,
                )
                or 0
            )
            id_socio = _clean_text(
                _row_value(
                    row,
                    "id_socio",
                    3,
                )
            )
            pin = _clean_text(
                _row_value(
                    row,
                    "pin",
                    0,
                )
            )
            member_since = _row_value(
                row,
                "member_since",
                1,
            )
            if (
                candidate_count == 1
                and id_socio
                and pin
                and member_since
            ):
                exact_map[
                    (
                        pin,
                        member_since,
                    )
                ] = id_socio

    if not exact_map:
        return {}

    last_visits: dict[str, date] = {}
    exact_keys = list(exact_map)

    for start in range(
        0,
        len(exact_keys),
        IDENTITY_BATCH_SIZE,
    ):
        chunk = exact_keys[
            start : start + IDENTITY_BATCH_SIZE
        ]

        rows = (
            db.session.query(
                WarehouseAttendanceVisitORM.member_pin,
                WarehouseAttendanceVisitORM.member_since,
                func.max(
                    WarehouseAttendanceVisitORM
                    .business_date
                ).label("last_visit_date"),
            )
            .filter(
                tuple_(
                    WarehouseAttendanceVisitORM.member_pin,
                    WarehouseAttendanceVisitORM.member_since,
                ).in_(chunk),
                WarehouseAttendanceVisitORM.attendance_type
                == "SOCIO",
                WarehouseAttendanceVisitORM.business_date
                < date_before,
            )
            .group_by(
                WarehouseAttendanceVisitORM.member_pin,
                WarehouseAttendanceVisitORM.member_since,
            )
            .all()
        )

        for row in rows:
            pin = _clean_text(
                _row_value(
                    row,
                    "member_pin",
                    0,
                )
            )
            member_since = _row_value(
                row,
                "member_since",
                1,
            )
            last_visit_date = _row_value(
                row,
                "last_visit_date",
                2,
            )
            id_socio = exact_map.get(
                (
                    pin,
                    member_since,
                )
            )
            if (
                id_socio
                and last_visit_date is not None
            ):
                current = last_visits.get(
                    id_socio
                )
                if (
                    current is None
                    or last_visit_date > current
                ):
                    last_visits[
                        id_socio
                    ] = last_visit_date

    return last_visits



def _serialize_member(
    member: _EligibleMember,
    *,
    has_visit: bool,
) -> dict[str, Any]:
    return {
        "id_socio": member.id_socio,
        "name": member.name,
        "branch_id": member.branch_id,
        "branch_name": member.branch_name,
        "pin": member.pin,
        "member_since": (
            member.member_since.isoformat()
            if member.member_since
            else None
        ),
        "has_visit": has_visit,
    }


def _frequency_metrics(
    state: _BaseHealthState,
    *,
    date_from: date,
    date_to: date,
) -> dict[str, Any]:
    frequencies = [
        _member_weekly_frequency(
            member,
            state.member_visit_stats.get(
                member.id_socio
            ),
            date_from=date_from,
            date_to=date_to,
        )
        for member in state.eligible_members.values()
    ]

    average = (
        sum(frequencies) / len(frequencies)
        if frequencies
        else 0.0
    )
    median_value = (
        median(frequencies)
        if frequencies
        else 0.0
    )

    buckets = [
        {
            "key": "ZERO",
            "label": "0 visitas",
            "count": 0,
        },
        {
            "key": "LT_1",
            "label": "Menos de 1 por semana",
            "count": 0,
        },
        {
            "key": "FROM_1_TO_1_99",
            "label": "1.00 a 1.99 por semana",
            "count": 0,
        },
        {
            "key": "FROM_2_TO_2_99",
            "label": "2.00 a 2.99 por semana",
            "count": 0,
        },
        {
            "key": "GTE_3",
            "label": "3.00 o más por semana",
            "count": 0,
        },
    ]

    for value in frequencies:
        if value == 0:
            bucket_index = 0
        elif value < 1:
            bucket_index = 1
        elif value < 2:
            bucket_index = 2
        elif value < 3:
            bucket_index = 3
        else:
            bucket_index = 4
        buckets[bucket_index]["count"] += 1

    total = len(frequencies)
    distribution = [
        {
            **bucket,
            "pct": (
                round(
                    bucket["count"] * 100 / total,
                    1,
                )
                if total
                else 0.0
            ),
        }
        for bucket in buckets
    ]

    return {
        "average_per_week": round(average, 2),
        "median_per_week": round(
            float(median_value),
            2,
        ),
        "distribution": distribution,
    }


def _member_weekly_frequency(
    member: _EligibleMember,
    visit_stats: _MemberVisitStats | None,
    *,
    date_from: date,
    date_to: date,
) -> float:
    eligible_days = _member_eligible_days(
        member,
        date_from=date_from,
        date_to=date_to,
    )
    if eligible_days <= 0:
        return 0.0

    visit_count = (
        visit_stats.visit_count
        if visit_stats is not None
        else 0
    )
    return visit_count * 7 / eligible_days


def _member_eligible_days(
    member: _EligibleMember,
    *,
    date_from: date,
    date_to: date,
) -> int:
    start = max(
        date_from,
        member.member_since or date_from,
    )
    end = min(
        date_to,
        member.expiration_date,
    )
    if end < start:
        return 0
    return (end - start).days + 1



def _recency_metrics(
    state: _BaseHealthState,
    *,
    date_to: date,
) -> dict[str, Any]:
    buckets = [
        {
            "key": "DAYS_0_7",
            "label": "0–7 días",
            "count": 0,
        },
        {
            "key": "DAYS_8_14",
            "label": "8–14 días",
            "count": 0,
        },
        {
            "key": "DAYS_15_21",
            "label": "15–21 días",
            "count": 0,
        },
        {
            "key": "DAYS_22_PLUS",
            "label": "22+ días",
            "count": 0,
        },
        {
            "key": "NO_RECORDED_VISIT",
            "label": "Sin visita registrada",
            "count": 0,
        },
    ]

    members_14_plus = 0

    for member in state.eligible_members.values():
        last_visit = (
            state.last_known_visit_by_member.get(
                member.id_socio
            )
        )

        if last_visit is None:
            buckets[4]["count"] += 1
            continue

        days = max(
            0,
            (date_to - last_visit).days,
        )

        if days >= 14:
            members_14_plus += 1

        if days <= 7:
            bucket_index = 0
        elif days <= 14:
            bucket_index = 1
        elif days <= 21:
            bucket_index = 2
        else:
            bucket_index = 3

        buckets[bucket_index]["count"] += 1

    total = len(state.eligible_members)
    distribution = [
        {
            **bucket,
            "pct": (
                round(
                    bucket["count"] * 100 / total,
                    1,
                )
                if total
                else 0.0
            ),
        }
        for bucket in buckets
    ]

    return {
        "members_14_plus_days_without_visit": (
            members_14_plus
        ),
        "distribution": distribution,
    }



def _positive_int(
    value: object,
    *,
    field_name: str,
    default: int,
) -> int:
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise SportsAnalysisValidationError(
            f"{field_name} inválido."
        ) from exc
    if parsed <= 0:
        raise SportsAnalysisValidationError(
            f"{field_name} inválido."
        )
    return parsed


def _row_value(
    row: Any,
    name: str,
    index: int,
) -> Any:
    mapping = getattr(
        row,
        "_mapping",
        None,
    )
    if mapping is not None and name in mapping:
        return mapping[name]

    try:
        return getattr(row, name)
    except (AttributeError, TypeError):
        pass

    try:
        return row[index]
    except (
        IndexError,
        KeyError,
        TypeError,
    ):
        return None


def _clean_text(value: Any) -> str | None:
    normalized = str(
        value or ""
    ).strip()
    return normalized or None
