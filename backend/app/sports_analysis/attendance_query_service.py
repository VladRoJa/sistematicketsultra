from __future__ import annotations

from collections import defaultdict
from datetime import date
from statistics import mean

from sqlalchemy import func, or_

from app.extensions import db
from app.models.attendance import (
    TrackAttendanceDailyMartORM,
    TrackAttendanceIntervalMartORM,
    WarehouseAttendanceRunORM,
    WarehouseAttendanceVisitORM,
)

from .attendance_access import (
    SportsAnalysisAuthorizationError,
    SportsAnalysisScope,
    scoped_branch_catalog,
)
from .attendance_mart_service import (
    ALL_ATTENDANCE_TYPES,
    BUCKET_MINUTES,
)


DEFAULT_ATTENDANCE_TYPE = "SOCIO"
MAX_RANGE_DAYS = 93
NON_OPERATIONAL_SOURCE_BRANCHES = ("CORP CDMX",)

AGE_BUCKETS = (
    ("0-17", 0, 17),
    ("18-24", 18, 24),
    ("25-34", 25, 34),
    ("35-44", 35, 44),
    ("45-54", 45, 54),
    ("55-64", 55, 64),
    ("65+", 65, 110),
)


class SportsAnalysisValidationError(ValueError):
    pass


def attendance_catalogs(
    scope: SportsAnalysisScope,
) -> dict:
    branches = scoped_branch_catalog(scope)
    branch_ids = tuple(
        item["id"] for item in branches
    )

    regions: dict[str, dict] = {}
    for branch in branches:
        region_key = branch.get("region_key")
        if not region_key:
            continue
        region = regions.setdefault(
            str(region_key),
            {
                "key": str(region_key),
                "name": (
                    branch.get("region_name")
                    or str(region_key)
                ),
                "branch_ids": [],
            },
        )
        region["branch_ids"].append(
            branch["id"]
        )

    attendance_types = []
    if branch_ids:
        attendance_types = [
            str(value)
            for (value,) in (
                db.session.query(
                    WarehouseAttendanceVisitORM
                    .attendance_type
                )
                .filter(
                    WarehouseAttendanceVisitORM
                    .sucursal_id.in_(branch_ids)
                )
                .distinct()
                .order_by(
                    WarehouseAttendanceVisitORM
                    .attendance_type
                )
                .all()
            )
            if value
        ]

    latest_date = _latest_business_date(
        branch_ids,
        DEFAULT_ATTENDANCE_TYPE,
    )

    return {
        "scope": {
            "role": scope.role,
            "is_global": scope.is_global,
            "allowed_branch_ids": list(
                scope.allowed_branch_ids
            ),
            "fixed_branch_id": (
                scope.fixed_branch_id
            ),
        },
        "branches": branches,
        "regions": list(regions.values()),
        "attendance_types": (
            [ALL_ATTENDANCE_TYPES]
            + attendance_types
        ),
        "default_attendance_type": (
            DEFAULT_ATTENDANCE_TYPE
        ),
        "latest_business_date": (
            latest_date.isoformat()
            if latest_date
            else None
        ),
    }


def attendance_dashboard(
    scope: SportsAnalysisScope,
    *,
    date_from: date | None,
    date_to: date | None,
    branch_id: int | None,
    region_key: str | None,
    attendance_type: str | None,
) -> dict:
    branches = scoped_branch_catalog(scope)
    effective_branch_ids = _effective_branch_ids(
        branches,
        branch_id=branch_id,
        region_key=region_key,
    )

    normalized_type = _normalize_attendance_type(
        attendance_type
    )

    latest_date = _latest_business_date(
        effective_branch_ids,
        normalized_type,
    )
    if latest_date is None:
        return _empty_dashboard(
            scope,
            date_from=date_from,
            date_to=date_to,
            branch_id=branch_id,
            region_key=region_key,
            attendance_type=normalized_type,
        )

    resolved_to = date_to or latest_date
    resolved_from = date_from or resolved_to

    _validate_date_range(
        resolved_from,
        resolved_to,
    )

    visit_query = _visit_query(
        effective_branch_ids,
        date_from=resolved_from,
        date_to=resolved_to,
        attendance_type=normalized_type,
    )

    visits = visit_query.count()
    unique_members = (
        visit_query.with_entities(
            func.count(
                func.distinct(
                    WarehouseAttendanceVisitORM
                    .member_pin
                )
            )
        )
        .filter(
            WarehouseAttendanceVisitORM
            .member_pin.isnot(None)
        )
        .scalar()
        or 0
    )

    closed_duration_query = (
        visit_query.with_entities(
            WarehouseAttendanceVisitORM
            .duration_seconds
        )
        .filter(
            WarehouseAttendanceVisitORM
            .visit_status
            == "CLOSED",
            WarehouseAttendanceVisitORM
            .duration_seconds.isnot(None),
        )
    )

    average_duration_seconds = (
        closed_duration_query.with_entities(
            func.avg(
                WarehouseAttendanceVisitORM
                .duration_seconds
            )
        ).scalar()
    )
    median_duration_seconds = (
        closed_duration_query.with_entities(
            func.percentile_cont(0.5)
            .within_group(
                WarehouseAttendanceVisitORM
                .duration_seconds
            )
        ).scalar()
    )

    interval_rows = _interval_rows(
        effective_branch_ids,
        date_from=resolved_from,
        date_to=resolved_to,
        attendance_type=normalized_type,
    )
    (
        occupancy_profile,
        entries_by_hour,
        peak,
    ) = _aggregate_intervals(interval_rows)

    branch_ranking = _branch_ranking(
        effective_branch_ids,
        branches,
        date_from=resolved_from,
        date_to=resolved_to,
        attendance_type=normalized_type,
    )

    age_distribution = _age_distribution(
        visit_query
    )
    attendance_type_distribution = (
        _attendance_type_distribution(
            effective_branch_ids,
            date_from=resolved_from,
            date_to=resolved_to,
        )
    )
    data_quality = _data_quality(
        visit_query,
        scope=scope,
        date_from=resolved_from,
        date_to=resolved_to,
        attendance_type=normalized_type,
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
            "date_from": (
                resolved_from.isoformat()
            ),
            "date_to": resolved_to.isoformat(),
            "branch_id": branch_id,
            "region_key": region_key,
            "attendance_type": normalized_type,
        },
        "summary": {
            "visits": int(visits),
            "unique_members": int(
                unique_members
            ),
            "peak_occupancy": int(
                peak["occupancy"]
            ),
            "peak_business_date": (
                peak["business_date"]
            ),
            "peak_minute": peak["minute"],
            "average_duration_seconds": (
                int(
                    round(
                        float(
                            average_duration_seconds
                        )
                    )
                )
                if average_duration_seconds
                is not None
                else None
            ),
            "median_duration_seconds": (
                int(
                    round(
                        float(
                            median_duration_seconds
                        )
                    )
                )
                if median_duration_seconds
                is not None
                else None
            ),
        },
        "occupancy_profile": occupancy_profile,
        "entries_by_hour": entries_by_hour,
        "age_distribution": age_distribution,
        "attendance_type_distribution": (
            attendance_type_distribution
        ),
        "branch_ranking": branch_ranking,
        "data_quality": data_quality,
    }


def attendance_runs(
    scope: SportsAnalysisScope,
    *,
    limit: int = 30,
) -> dict:
    if not scope.is_global:
        raise SportsAnalysisAuthorizationError(
            "El historial de ingestas está "
            "reservado a perfiles globales."
        )

    safe_limit = max(
        1,
        min(int(limit), 100),
    )
    rows = (
        db.session.query(
            WarehouseAttendanceRunORM
        )
        .order_by(
            WarehouseAttendanceRunORM
            .started_at_utc.desc()
        )
        .limit(safe_limit)
        .all()
    )

    return {
        "items": [
            {
                "id": int(row.id),
                "business_date": (
                    row.business_date.isoformat()
                ),
                "status": row.status,
                "trigger_source": (
                    row.trigger_source
                ),
                "source_rows": int(
                    row.source_rows
                ),
                "inserted_rows": int(
                    row.inserted_rows
                ),
                "updated_rows": int(
                    row.updated_rows
                ),
                "rejected_rows": int(
                    row.rejected_rows
                ),
                "started_at_utc": (
                    row.started_at_utc.isoformat()
                    if row.started_at_utc
                    else None
                ),
                "finished_at_utc": (
                    row.finished_at_utc.isoformat()
                    if row.finished_at_utc
                    else None
                ),
                "error_message": (
                    str(row.error_message)
                    .splitlines()[0][:500]
                    if row.error_message
                    else None
                ),
            }
            for row in rows
        ]
    }


def _effective_branch_ids(
    branches: list[dict],
    *,
    branch_id: int | None,
    region_key: str | None,
) -> tuple[int, ...]:
    available = {
        int(item["id"]): item
        for item in branches
    }

    if branch_id is not None:
        if branch_id not in available:
            raise SportsAnalysisAuthorizationError(
                "Sucursal fuera del alcance "
                "autorizado."
            )
        if (
            region_key
            and str(
                available[branch_id].get(
                    "region_key"
                )
            )
            != region_key
        ):
            raise SportsAnalysisValidationError(
                "La sucursal no pertenece "
                "a la región seleccionada."
            )
        return (branch_id,)

    if region_key:
        ids = tuple(
            item["id"]
            for item in branches
            if str(
                item.get("region_key") or ""
            )
            == region_key
        )
        if not ids:
            raise SportsAnalysisValidationError(
                "Región inválida o fuera "
                "del alcance autorizado."
            )
        return ids

    return tuple(
        item["id"]
        for item in branches
    )


def _normalize_attendance_type(
    value: str | None,
) -> str:
    normalized = str(
        value or DEFAULT_ATTENDANCE_TYPE
    ).strip().upper()
    if not normalized:
        return DEFAULT_ATTENDANCE_TYPE
    return normalized[:100]


def _validate_date_range(
    date_from: date,
    date_to: date,
) -> None:
    if date_from > date_to:
        raise SportsAnalysisValidationError(
            "date_from no puede ser posterior "
            "a date_to."
        )
    days = (date_to - date_from).days + 1
    if days > MAX_RANGE_DAYS:
        raise SportsAnalysisValidationError(
            f"El rango máximo inicial es de "
            f"{MAX_RANGE_DAYS} días."
        )


def _latest_business_date(
    branch_ids: tuple[int, ...],
    attendance_type: str,
) -> date | None:
    if not branch_ids:
        return None

    return (
        db.session.query(
            func.max(
                TrackAttendanceDailyMartORM
                .business_date
            )
        )
        .filter(
            TrackAttendanceDailyMartORM
            .sucursal_id.in_(branch_ids),
            TrackAttendanceDailyMartORM
            .attendance_type
            == attendance_type,
        )
        .scalar()
    )


def _visit_query(
    branch_ids: tuple[int, ...],
    *,
    date_from: date,
    date_to: date,
    attendance_type: str,
):
    query = (
        db.session.query(
            WarehouseAttendanceVisitORM
        )
        .filter(
            WarehouseAttendanceVisitORM
            .sucursal_id.in_(
                branch_ids or (-1,)
            ),
            WarehouseAttendanceVisitORM
            .business_date.between(
                date_from,
                date_to,
            ),
        )
    )
    if attendance_type != ALL_ATTENDANCE_TYPES:
        query = query.filter(
            WarehouseAttendanceVisitORM
            .attendance_type
            == attendance_type
        )
    return query


def _interval_rows(
    branch_ids: tuple[int, ...],
    *,
    date_from: date,
    date_to: date,
    attendance_type: str,
):
    return (
        db.session.query(
            TrackAttendanceIntervalMartORM
        )
        .filter(
            TrackAttendanceIntervalMartORM
            .sucursal_id.in_(
                branch_ids or (-1,)
            ),
            TrackAttendanceIntervalMartORM
            .business_date.between(
                date_from,
                date_to,
            ),
            TrackAttendanceIntervalMartORM
            .attendance_type
            == attendance_type,
        )
        .all()
    )


def _aggregate_intervals(
    rows: list[
        TrackAttendanceIntervalMartORM
    ],
) -> tuple[list[dict], list[dict], dict]:
    by_day_bucket: dict[
        tuple[date, int],
        dict[str, int],
    ] = defaultdict(
        lambda: {
            "occupancy": 0,
            "entries": 0,
            "exits": 0,
        }
    )
    dates: set[date] = set()

    for row in rows:
        key = (
            row.business_date,
            int(row.bucket_minute),
        )
        dates.add(row.business_date)
        target = by_day_bucket[key]
        target["occupancy"] += int(
            row.occupancy
        )
        target["entries"] += int(
            row.entries
        )
        target["exits"] += int(
            row.exits
        )

    date_count = len(dates)
    occupancy_profile = []
    hourly_entries = [0] * 24
    peak = {
        "occupancy": 0,
        "business_date": None,
        "minute": None,
    }

    for (
        business_date,
        minute,
    ), values in by_day_bucket.items():
        if (
            values["occupancy"]
            > peak["occupancy"]
        ):
            peak = {
                "occupancy": values[
                    "occupancy"
                ],
                "business_date": (
                    business_date.isoformat()
                ),
                "minute": minute,
            }
        hourly_entries[
            minute // 60
        ] += values["entries"]

    for minute in range(
        0,
        24 * 60,
        BUCKET_MINUTES,
    ):
        day_values = [
            by_day_bucket.get(
                (business_date, minute),
                {
                    "occupancy": 0,
                    "entries": 0,
                    "exits": 0,
                },
            )
            for business_date in dates
        ]
        occupancy_profile.append(
            {
                "minute": minute,
                "occupancy": (
                    round(
                        mean(
                            item["occupancy"]
                            for item in day_values
                        ),
                        1,
                    )
                    if date_count
                    else 0
                ),
                "entries": sum(
                    item["entries"]
                    for item in day_values
                ),
                "exits": sum(
                    item["exits"]
                    for item in day_values
                ),
            }
        )

    entries_by_hour = [
        {
            "hour": hour,
            "entries": hourly_entries[hour],
        }
        for hour in range(24)
    ]

    return (
        occupancy_profile,
        entries_by_hour,
        peak,
    )


def _age_distribution(
    visit_query,
) -> list[dict]:
    rows = (
        visit_query.with_entities(
            WarehouseAttendanceVisitORM.age,
            func.count(
                WarehouseAttendanceVisitORM.id
            ),
        )
        .filter(
            WarehouseAttendanceVisitORM
            .age_is_valid.is_(True),
            WarehouseAttendanceVisitORM
            .age.isnot(None),
        )
        .group_by(
            WarehouseAttendanceVisitORM.age
        )
        .all()
    )

    result = {
        label: 0
        for label, _, _ in AGE_BUCKETS
    }
    for age, count in rows:
        numeric_age = int(age)
        for (
            label,
            minimum,
            maximum,
        ) in AGE_BUCKETS:
            if (
                minimum
                <= numeric_age
                <= maximum
            ):
                result[label] += int(count)
                break

    return [
        {
            "label": label,
            "visits": result[label],
        }
        for label, _, _ in AGE_BUCKETS
    ]


def _attendance_type_distribution(
    branch_ids: tuple[int, ...],
    *,
    date_from: date,
    date_to: date,
) -> list[dict]:
    rows = (
        db.session.query(
            WarehouseAttendanceVisitORM
            .attendance_type,
            func.count(
                WarehouseAttendanceVisitORM.id
            ),
        )
        .filter(
            WarehouseAttendanceVisitORM
            .sucursal_id.in_(
                branch_ids or (-1,)
            ),
            WarehouseAttendanceVisitORM
            .business_date.between(
                date_from,
                date_to,
            ),
        )
        .group_by(
            WarehouseAttendanceVisitORM
            .attendance_type
        )
        .order_by(
            func.count(
                WarehouseAttendanceVisitORM.id
            ).desc()
        )
        .all()
    )
    return [
        {
            "attendance_type": str(
                attendance_type
            ),
            "visits": int(count),
        }
        for attendance_type, count in rows
    ]


def _branch_ranking(
    branch_ids: tuple[int, ...],
    branches: list[dict],
    *,
    date_from: date,
    date_to: date,
    attendance_type: str,
) -> list[dict]:
    rows = (
        db.session.query(
            TrackAttendanceDailyMartORM
        )
        .filter(
            TrackAttendanceDailyMartORM
            .sucursal_id.in_(
                branch_ids or (-1,)
            ),
            TrackAttendanceDailyMartORM
            .business_date.between(
                date_from,
                date_to,
            ),
            TrackAttendanceDailyMartORM
            .attendance_type
            == attendance_type,
        )
        .all()
    )

    aggregates: dict[
        int,
        dict,
    ] = defaultdict(
        lambda: {
            "visits": 0,
            "peak_occupancy": 0,
        }
    )
    for row in rows:
        target = aggregates[
            int(row.sucursal_id)
        ]
        target["visits"] += int(
            row.visits
        )
        target["peak_occupancy"] = max(
            target["peak_occupancy"],
            int(row.peak_occupancy),
        )

    unique_rows = (
        _visit_query(
            branch_ids,
            date_from=date_from,
            date_to=date_to,
            attendance_type=attendance_type,
        )
        .with_entities(
            WarehouseAttendanceVisitORM
            .sucursal_id,
            func.count(
                func.distinct(
                    WarehouseAttendanceVisitORM
                    .member_pin
                )
            ),
        )
        .filter(
            WarehouseAttendanceVisitORM
            .member_pin.isnot(None)
        )
        .group_by(
            WarehouseAttendanceVisitORM
            .sucursal_id
        )
        .all()
    )
    unique_by_branch = {
        int(branch_id): int(count)
        for branch_id, count in unique_rows
        if branch_id is not None
    }

    branch_by_id = {
        int(item["id"]): item
        for item in branches
    }

    result = []
    for (
        branch_id,
        values,
    ) in aggregates.items():
        branch = branch_by_id.get(
            branch_id,
            {},
        )
        result.append(
            {
                "branch_id": branch_id,
                "branch_name": (
                    branch.get("name")
                    or str(branch_id)
                ),
                "region_key": (
                    branch.get("region_key")
                ),
                "visits": values[
                    "visits"
                ],
                "unique_members": (
                    unique_by_branch.get(
                        branch_id,
                        0,
                    )
                ),
                "peak_occupancy": values[
                    "peak_occupancy"
                ],
            }
        )

    return sorted(
        result,
        key=lambda item: (
            -item["visits"],
            item["branch_name"],
        ),
    )


def _data_quality(
    visit_query,
    *,
    scope: SportsAnalysisScope,
    date_from: date,
    date_to: date,
    attendance_type: str,
) -> dict:
    rows = (
        visit_query.with_entities(
            WarehouseAttendanceVisitORM
            .visit_status,
            func.count(
                WarehouseAttendanceVisitORM.id
            ),
        )
        .group_by(
            WarehouseAttendanceVisitORM
            .visit_status
        )
        .all()
    )
    by_status = {
        str(status): int(count)
        for status, count in rows
    }

    unresolved_visits = 0
    non_operational_excluded = 0
    if scope.is_global:
        unresolved_query = (
            db.session.query(
                func.count(
                    WarehouseAttendanceVisitORM.id
                )
            )
            .filter(
                WarehouseAttendanceVisitORM
                .business_date.between(
                    date_from,
                    date_to,
                ),
                WarehouseAttendanceVisitORM
                .sucursal_id.is_(None),
                or_(
                    WarehouseAttendanceVisitORM
                    .source_branch_name.is_(None),
                    WarehouseAttendanceVisitORM
                    .source_branch_name.notin_(
                        NON_OPERATIONAL_SOURCE_BRANCHES
                    ),
                ),
            )
        )
        non_operational_query = (
            db.session.query(
                func.count(
                    WarehouseAttendanceVisitORM.id
                )
            )
            .filter(
                WarehouseAttendanceVisitORM
                .business_date.between(
                    date_from,
                    date_to,
                ),
                WarehouseAttendanceVisitORM
                .sucursal_id.is_(None),
                WarehouseAttendanceVisitORM
                .source_branch_name.in_(
                    NON_OPERATIONAL_SOURCE_BRANCHES
                ),
            )
        )
        if (
            attendance_type
            != ALL_ATTENDANCE_TYPES
        ):
            unresolved_query = (
                unresolved_query.filter(
                    WarehouseAttendanceVisitORM
                    .attendance_type
                    == attendance_type
                )
            )
            non_operational_query = (
                non_operational_query.filter(
                    WarehouseAttendanceVisitORM
                    .attendance_type
                    == attendance_type
                )
            )
        unresolved_visits = (
            unresolved_query.scalar()
            or 0
        )
        non_operational_excluded = (
            non_operational_query.scalar()
            or 0
        )

    return {
        "closed": by_status.get(
            "CLOSED",
            0,
        ),
        "open": by_status.get("OPEN", 0),
        "cross_day": by_status.get(
            "CROSS_DAY",
            0,
        ),
        "invalid_time": by_status.get(
            "INVALID_TIME",
            0,
        ),
        "unresolved_branch": int(
            unresolved_visits
        ),
        "non_operational_excluded": int(
            non_operational_excluded
        ),
    }


def _empty_dashboard(
    scope: SportsAnalysisScope,
    *,
    date_from: date | None,
    date_to: date | None,
    branch_id: int | None,
    region_key: str | None,
    attendance_type: str,
) -> dict:
    return {
        "scope": {
            "role": scope.role,
            "is_global": scope.is_global,
            "allowed_branch_ids": list(
                scope.allowed_branch_ids
            ),
        },
        "filters": {
            "date_from": (
                date_from.isoformat()
                if date_from
                else None
            ),
            "date_to": (
                date_to.isoformat()
                if date_to
                else None
            ),
            "branch_id": branch_id,
            "region_key": region_key,
            "attendance_type": attendance_type,
        },
        "summary": {
            "visits": 0,
            "unique_members": 0,
            "peak_occupancy": 0,
            "peak_business_date": None,
            "peak_minute": None,
            "average_duration_seconds": None,
            "median_duration_seconds": None,
        },
        "occupancy_profile": [],
        "entries_by_hour": [],
        "age_distribution": [],
        "attendance_type_distribution": [],
        "branch_ranking": [],
        "data_quality": {
            "closed": 0,
            "open": 0,
            "cross_day": 0,
            "invalid_time": 0,
            "unresolved_branch": 0,
            "non_operational_excluded": 0,
        },
    }
