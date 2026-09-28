from __future__ import annotations

from datetime import date
from io import BytesIO
from math import ceil
from zoneinfo import ZoneInfo

from sqlalchemy import asc, desc, func

from app.extensions import db
from app.models.attendance import (
    TrackAttendanceIntervalMartORM,
    WarehouseAttendanceVisitORM,
)
from app.models.sucursal_model import Sucursal

from .attendance_access import (
    SportsAnalysisScope,
    scoped_branch_catalog,
)
from .attendance_export_service import (
    ATTENDANCE_EXPORT_MIMETYPE,
    build_attendance_workbook,
)
from .attendance_identity_service import (
    AttendanceIdentityResolution,
    resolve_attendance_identities,
)
from .attendance_mart_service import (
    ALL_ATTENDANCE_TYPES,
)
from .attendance_query_service import (
    AGE_BUCKETS,
    SportsAnalysisValidationError,
    _effective_branch_ids,
    _normalize_attendance_type,
    _validate_date_range,
    attendance_dashboard,
)


DETAIL_EXPORT_MIMETYPE = ATTENDANCE_EXPORT_MIMETYPE
DETAIL_TIMEZONE_NAME = "America/Tijuana"
DETAIL_TIMEZONE = ZoneInfo(DETAIL_TIMEZONE_NAME)
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

_VISIT_COLUMNS = [
    {"key": "business_date", "label": "Fecha"},
    {"key": "branch_name", "label": "Sucursal"},
    {
        "key": "display_name",
        "label": "Nombre",
        "sortable": False,
    },
    {
        "key": "id_socio",
        "label": "ID Socio",
        "sortable": False,
    },
    {"key": "member_pin", "label": "PIN"},
    {"key": "entered_at", "label": "Entrada"},
    {"key": "exited_at", "label": "Salida"},
    {"key": "visit_status", "label": "Estado"},
    {"key": "duration_minutes", "label": "Estancia (min)"},
    {"key": "age", "label": "Edad"},
    {"key": "city", "label": "Ciudad"},
    {"key": "postal_code", "label": "CP"},
    {"key": "member_since", "label": "Alta"},
    {"key": "attendance_type", "label": "Tipo asistencia"},
    {"key": "has_opening", "label": "Tiene apertura"},
    {"key": "source_branch_name", "label": "Sucursal origen"},
]

_UNIQUE_COLUMNS = [
    {"key": "member_pin", "label": "PIN"},
    {"key": "visits", "label": "Visitas"},
    {"key": "first_entered_at", "label": "Primera entrada"},
    {"key": "last_entered_at", "label": "Última entrada"},
    {"key": "branches_count", "label": "Sucursales"},
]

_INTERVAL_COLUMNS = [
    {"key": "business_date", "label": "Fecha"},
    {"key": "branch_name", "label": "Sucursal"},
    {"key": "bucket_time", "label": "Hora"},
    {"key": "occupancy", "label": "Aforo intervalo"},
    {"key": "entries", "label": "Entradas"},
    {"key": "exits", "label": "Salidas"},
    {"key": "attendance_type", "label": "Público"},
]

_VISIT_SORTS = {
    "business_date": WarehouseAttendanceVisitORM.business_date,
    "branch_name": Sucursal.sucursal,
    "member_pin": WarehouseAttendanceVisitORM.member_pin,
    "entered_at": WarehouseAttendanceVisitORM.entered_at_utc,
    "exited_at": WarehouseAttendanceVisitORM.exited_at_utc,
    "visit_status": WarehouseAttendanceVisitORM.visit_status,
    "duration_minutes": WarehouseAttendanceVisitORM.duration_seconds,
    "age": WarehouseAttendanceVisitORM.age,
    "city": WarehouseAttendanceVisitORM.city,
    "postal_code": WarehouseAttendanceVisitORM.postal_code,
    "member_since": WarehouseAttendanceVisitORM.member_since,
    "attendance_type": WarehouseAttendanceVisitORM.attendance_type,
    "has_opening": WarehouseAttendanceVisitORM.has_opening,
    "source_branch_name": WarehouseAttendanceVisitORM.source_branch_name,
}

_UNIQUE_PIN = WarehouseAttendanceVisitORM.member_pin.label(
    "member_pin"
)
_UNIQUE_VISITS = func.count(
    WarehouseAttendanceVisitORM.id
).label("visits")
_UNIQUE_FIRST = func.min(
    WarehouseAttendanceVisitORM.entered_at_utc
).label("first_entered_at")
_UNIQUE_LAST = func.max(
    WarehouseAttendanceVisitORM.entered_at_utc
).label("last_entered_at")
_UNIQUE_BRANCHES = func.count(
    func.distinct(
        WarehouseAttendanceVisitORM.sucursal_id
    )
).label("branches_count")

_UNIQUE_SORTS = {
    "member_pin": _UNIQUE_PIN,
    "visits": _UNIQUE_VISITS,
    "first_entered_at": _UNIQUE_FIRST,
    "last_entered_at": _UNIQUE_LAST,
    "branches_count": _UNIQUE_BRANCHES,
}

_INTERVAL_SORTS = {
    "business_date": TrackAttendanceIntervalMartORM.business_date,
    "branch_name": Sucursal.sucursal,
    "bucket_time": TrackAttendanceIntervalMartORM.bucket_minute,
    "occupancy": TrackAttendanceIntervalMartORM.occupancy,
    "entries": TrackAttendanceIntervalMartORM.entries,
    "exits": TrackAttendanceIntervalMartORM.exits,
    "attendance_type": TrackAttendanceIntervalMartORM.attendance_type,
}

_SUPPORTED_METRICS = {
    "visits",
    "unique_members",
    "duration",
    "peak_occupancy",
    "occupancy_interval",
    "entries_hour",
    "age_bucket",
    "attendance_type",
}


def build_attendance_detail(
    scope: SportsAnalysisScope,
    *,
    metric: str,
    date_from: date,
    date_to: date,
    branch_id: int | None,
    region_key: str | None,
    attendance_type: str | None,
    page: object = 1,
    page_size: object = DEFAULT_PAGE_SIZE,
    sort_by: str | None = None,
    sort_dir: str | None = None,
    minute: int | None = None,
    hour: int | None = None,
    age_bucket: str | None = None,
) -> dict:
    normalized_metric = _normalize_metric(metric)
    _validate_metric(normalized_metric)

    safe_page = _parse_positive_int(
        page,
        "page",
        default=1,
    )
    safe_page_size = min(
        _parse_positive_int(
            page_size,
            "page_size",
            default=DEFAULT_PAGE_SIZE,
        ),
        MAX_PAGE_SIZE,
    )

    dataset = _build_dataset(
        scope,
        metric=normalized_metric,
        date_from=date_from,
        date_to=date_to,
        branch_id=branch_id,
        region_key=region_key,
        attendance_type=attendance_type,
        minute=minute,
        hour=hour,
        age_bucket=age_bucket,
    )

    safe_sort_by = _normalize_sort_by(
        sort_by,
        dataset["sorts"],
        default=dataset["default_sort"],
    )
    safe_sort_dir = _normalize_sort_dir(
        sort_dir,
        default=dataset["default_dir"],
    )

    count = int(dataset["count"]())
    total_pages = max(
        1,
        ceil(count / safe_page_size),
    )
    safe_page = min(
        safe_page,
        total_pages,
    )

    rows = (
        _apply_sort(
            dataset["query"],
            sorts=dataset["sorts"],
            sort_by=safe_sort_by,
            sort_dir=safe_sort_dir,
            tie_breaker=dataset["tie_breaker"],
        )
        .offset(
            (safe_page - 1)
            * safe_page_size
        )
        .limit(safe_page_size)
        .all()
    )

    serialized_rows = _serialize_dataset_rows(
        dataset,
        rows,
    )

    return {
        "metric": normalized_metric,
        "title": dataset["title"],
        "count": count,
        "page": safe_page,
        "page_size": safe_page_size,
        "total_pages": total_pages,
        "sort_by": safe_sort_by,
        "sort_dir": safe_sort_dir,
        "columns": list(dataset["columns"]),
        "rows": serialized_rows,
    }


def build_attendance_detail_export(
    scope: SportsAnalysisScope,
    *,
    metric: str,
    date_from: date,
    date_to: date,
    branch_id: int | None,
    region_key: str | None,
    attendance_type: str | None,
    sort_by: str | None = None,
    sort_dir: str | None = None,
    minute: int | None = None,
    hour: int | None = None,
    age_bucket: str | None = None,
) -> tuple[BytesIO, str]:
    normalized_metric = _normalize_metric(metric)
    _validate_metric(normalized_metric)

    dataset = _build_dataset(
        scope,
        metric=normalized_metric,
        date_from=date_from,
        date_to=date_to,
        branch_id=branch_id,
        region_key=region_key,
        attendance_type=attendance_type,
        minute=minute,
        hour=hour,
        age_bucket=age_bucket,
    )

    safe_sort_by = _normalize_sort_by(
        sort_by,
        dataset["sorts"],
        default=dataset["default_sort"],
    )
    safe_sort_dir = _normalize_sort_dir(
        sort_dir,
        default=dataset["default_dir"],
    )

    rows = (
        _apply_sort(
            dataset["query"],
            sorts=dataset["sorts"],
            sort_by=safe_sort_by,
            sort_dir=safe_sort_dir,
            tie_breaker=dataset["tie_breaker"],
        )
        .all()
    )
    serialized_rows = _serialize_dataset_rows(
        dataset,
        rows,
    )

    output = build_attendance_workbook(
        columns=dataset["columns"],
        rows=serialized_rows,
        sheet_name=dataset["sheet_name"],
    )

    date_fragment = (
        date_from.isoformat()
        if date_from == date_to
        else (
            f"{date_from.isoformat()}_"
            f"{date_to.isoformat()}"
        )
    )
    filename = (
        "aforo_asistencia_"
        f"{normalized_metric}_"
        f"{date_fragment}.xlsx"
    )
    return output, filename


def _build_dataset(
    scope: SportsAnalysisScope,
    *,
    metric: str,
    date_from: date,
    date_to: date,
    branch_id: int | None,
    region_key: str | None,
    attendance_type: str | None,
    minute: int | None,
    hour: int | None,
    age_bucket: str | None,
) -> dict:
    _validate_date_range(
        date_from,
        date_to,
    )

    branches = scoped_branch_catalog(scope)
    branch_ids = _effective_branch_ids(
        branches,
        branch_id=branch_id,
        region_key=region_key,
    )
    normalized_type = _normalize_attendance_type(
        attendance_type
    )

    if metric == "unique_members":
        return _unique_dataset(
            branch_ids,
            date_from=date_from,
            date_to=date_to,
            attendance_type=normalized_type,
            age_bucket=age_bucket,
        )

    if metric in {
        "peak_occupancy",
        "occupancy_interval",
    }:
        return _interval_dataset(
            scope,
            branch_ids,
            metric=metric,
            date_from=date_from,
            date_to=date_to,
            branch_id=branch_id,
            region_key=region_key,
            attendance_type=normalized_type,
            minute=minute,
        )

    query = _visit_rows_query(
        branch_ids,
        date_from=date_from,
        date_to=date_to,
        attendance_type=normalized_type,
    )

    title = "Visitas registradas"

    if metric == "duration":
        query = query.filter(
            WarehouseAttendanceVisitORM.visit_status
            == "CLOSED",
            WarehouseAttendanceVisitORM.duration_seconds
            .isnot(None),
        )
        title = "Estancias que construyen promedio y mediana"

    elif metric == "entries_hour":
        if hour is None or hour < 0 or hour > 23:
            raise SportsAnalysisValidationError(
                "hour debe estar entre 0 y 23."
            )
        local_entry = func.timezone(
            DETAIL_TIMEZONE_NAME,
            WarehouseAttendanceVisitORM.entered_at_utc,
        )
        query = query.filter(
            func.extract(
                "hour",
                local_entry,
            )
            == hour
        )
        title = (
            "Entradas de "
            f"{hour:02d}:00 a "
            f"{hour:02d}:59"
        )

    elif metric == "age_bucket":
        minimum, maximum = _resolve_age_bucket(
            age_bucket
        )
        query = query.filter(
            WarehouseAttendanceVisitORM.age_is_valid
            .is_(True),
            WarehouseAttendanceVisitORM.age
            .isnot(None),
            WarehouseAttendanceVisitORM.age
            >= minimum,
            WarehouseAttendanceVisitORM.age
            <= maximum,
        )
        title = (
            "Visitas del rango de edad "
            f"{age_bucket}"
        )

    elif metric == "attendance_type":
        title = (
            "Visitas por tipo de asistencia: "
            f"{normalized_type}"
        )

    return {
        "title": title,
        "columns": _VISIT_COLUMNS,
        "query": query,
        "count": (
            lambda: query.order_by(None).count()
        ),
        "sorts": _VISIT_SORTS,
        "default_sort": "entered_at",
        "default_dir": "asc",
        "tie_breaker": (
            WarehouseAttendanceVisitORM.id
        ),
        "serialize": _serialize_visit_row,
        "sheet_name": "Detalle",
        "identity_enrichment": True,
    }


def _visit_rows_query(
    branch_ids: tuple[int, ...],
    *,
    date_from: date,
    date_to: date,
    attendance_type: str,
):
    query = (
        db.session.query(
            WarehouseAttendanceVisitORM,
            Sucursal.sucursal,
        )
        .join(
            Sucursal,
            Sucursal.sucursal_id
            == WarehouseAttendanceVisitORM.sucursal_id,
        )
        .filter(
            WarehouseAttendanceVisitORM.sucursal_id
            .in_(branch_ids or (-1,)),
            WarehouseAttendanceVisitORM.business_date
            .between(
                date_from,
                date_to,
            ),
        )
    )

    if attendance_type != ALL_ATTENDANCE_TYPES:
        query = query.filter(
            WarehouseAttendanceVisitORM.attendance_type
            == attendance_type
        )

    return query


def _unique_dataset(
    branch_ids: tuple[int, ...],
    *,
    date_from: date,
    date_to: date,
    attendance_type: str,
    age_bucket: str | None,
) -> dict:
    base_filters = [
        WarehouseAttendanceVisitORM.sucursal_id
        .in_(branch_ids or (-1,)),
        WarehouseAttendanceVisitORM.business_date
        .between(
            date_from,
            date_to,
        ),
        WarehouseAttendanceVisitORM.member_pin
        .isnot(None),
    ]
    if attendance_type != ALL_ATTENDANCE_TYPES:
        base_filters.append(
            WarehouseAttendanceVisitORM.attendance_type
            == attendance_type
        )

    title = "Personas únicas por PIN"
    if age_bucket:
        minimum, maximum = _resolve_age_bucket(
            age_bucket
        )
        base_filters.extend(
            [
                WarehouseAttendanceVisitORM
                .age_is_valid.is_(True),
                WarehouseAttendanceVisitORM
                .age.isnot(None),
                WarehouseAttendanceVisitORM.age
                >= minimum,
                WarehouseAttendanceVisitORM.age
                <= maximum,
            ]
        )
        title = (
            "Personas únicas del rango de edad "
            f"{age_bucket}"
        )

    query = (
        db.session.query(
            _UNIQUE_PIN,
            _UNIQUE_VISITS,
            _UNIQUE_FIRST,
            _UNIQUE_LAST,
            _UNIQUE_BRANCHES,
        )
        .filter(*base_filters)
        .group_by(
            WarehouseAttendanceVisitORM.member_pin
        )
    )

    def count_unique():
        return (
            db.session.query(
                func.count(
                    func.distinct(
                        WarehouseAttendanceVisitORM.member_pin
                    )
                )
            )
            .filter(*base_filters)
            .scalar()
            or 0
        )

    return {
        "title": title,
        "columns": _UNIQUE_COLUMNS,
        "query": query,
        "count": count_unique,
        "sorts": _UNIQUE_SORTS,
        "default_sort": "member_pin",
        "default_dir": "asc",
        "tie_breaker": _UNIQUE_PIN,
        "serialize": _serialize_unique_row,
        "sheet_name": "Personas únicas",
    }


def _interval_dataset(
    scope: SportsAnalysisScope,
    branch_ids: tuple[int, ...],
    *,
    metric: str,
    date_from: date,
    date_to: date,
    branch_id: int | None,
    region_key: str | None,
    attendance_type: str,
    minute: int | None,
) -> dict:
    target_date: date | None = None
    target_minute = minute

    if metric == "peak_occupancy":
        dashboard = attendance_dashboard(
            scope,
            date_from=date_from,
            date_to=date_to,
            branch_id=branch_id,
            region_key=region_key,
            attendance_type=attendance_type,
        )
        peak_date_raw = dashboard[
            "summary"
        ]["peak_business_date"]
        target_minute = dashboard[
            "summary"
        ]["peak_minute"]

        if peak_date_raw:
            target_date = date.fromisoformat(
                peak_date_raw
            )

    if (
        target_minute is None
        or target_minute < 0
        or target_minute >= 1440
        or target_minute % 15 != 0
    ):
        raise SportsAnalysisValidationError(
            "minute debe ser un intervalo válido "
            "de 15 minutos."
        )

    query = (
        db.session.query(
            TrackAttendanceIntervalMartORM,
            Sucursal.sucursal,
        )
        .join(
            Sucursal,
            Sucursal.sucursal_id
            == TrackAttendanceIntervalMartORM.sucursal_id,
        )
        .filter(
            TrackAttendanceIntervalMartORM.sucursal_id
            .in_(branch_ids or (-1,)),
            TrackAttendanceIntervalMartORM.business_date
            .between(
                date_from,
                date_to,
            ),
            TrackAttendanceIntervalMartORM.attendance_type
            == attendance_type,
            TrackAttendanceIntervalMartORM.bucket_minute
            == target_minute,
        )
    )

    if target_date is not None:
        query = query.filter(
            TrackAttendanceIntervalMartORM.business_date
            == target_date
        )

    title = (
        "Contribuciones del aforo pico"
        if metric == "peak_occupancy"
        else (
            "Contribuciones de aforo · "
            f"{_format_minute(target_minute)}"
        )
    )

    return {
        "title": title,
        "columns": _INTERVAL_COLUMNS,
        "query": query,
        "count": (
            lambda: query.order_by(None).count()
        ),
        "sorts": _INTERVAL_SORTS,
        "default_sort": "occupancy",
        "default_dir": "desc",
        "tie_breaker": (
            TrackAttendanceIntervalMartORM.id
        ),
        "serialize": _serialize_interval_row,
        "sheet_name": "Aforo",
    }


def _apply_sort(
    query,
    *,
    sorts: dict,
    sort_by: str,
    sort_dir: str,
    tie_breaker,
):
    sort_expression = sorts[sort_by]
    order = (
        asc
        if sort_dir == "asc"
        else desc
    )
    return query.order_by(
        order(sort_expression),
        asc(tie_breaker),
    )


def _serialize_dataset_rows(
    dataset: dict,
    rows: list,
) -> list[dict]:
    if not dataset.get(
        "identity_enrichment",
        False,
    ):
        return [
            dataset["serialize"](row)
            for row in rows
        ]

    visits = [
        row[0]
        for row in rows
    ]
    identities = resolve_attendance_identities(
        visits,
        session=db.session,
    )

    serialized_rows: list[dict] = []
    for row in rows:
        visit = row[0]
        identity = identities.get(
            int(visit.id)
        )
        serialized_rows.append(
            dataset["serialize"](
                row,
                identity,
            )
        )

    return serialized_rows


def _serialize_visit_row(
    row,
    identity: AttendanceIdentityResolution
    | None = None,
) -> dict:
    visit, branch_name = row
    duration_minutes = (
        round(
            float(visit.duration_seconds)
            / 60,
            1,
        )
        if visit.duration_seconds
        is not None
        else None
    )

    return {
        "business_date": _format_date(
            visit.business_date
        ),
        "branch_name": str(
            branch_name
            or visit.source_branch_name
        ),
        "display_name": (
            identity.display_name
            if identity is not None
            else _source_member_name(visit)
        ),
        "id_socio": (
            identity.id_socio
            if identity is not None
            else None
        ),
        "member_pin": visit.member_pin,
        "identity_method": (
            identity.identity_method
            if identity is not None
            else None
        ),
        "identity_snapshot_id": (
            identity.source_snapshot_id
            if identity is not None
            else None
        ),
        "entered_at": _format_datetime(
            visit.entered_at_utc
        ),
        "exited_at": _format_datetime(
            visit.exited_at_utc
        ),
        "visit_status": visit.visit_status,
        "duration_minutes": duration_minutes,
        "age": (
            int(visit.age)
            if visit.age is not None
            else None
        ),
        "city": visit.city,
        "postal_code": visit.postal_code,
        "member_since": _format_date(
            visit.member_since
        ),
        "attendance_type": (
            visit.attendance_type
        ),
        "has_opening": (
            "Sí"
            if visit.has_opening is True
            else "No"
            if visit.has_opening is False
            else None
        ),
        "source_branch_name": (
            visit.source_branch_name
        ),
    }


def _source_member_name(
    visit: WarehouseAttendanceVisitORM,
) -> str | None:
    parts = [
        str(value).strip()
        for value in (
            visit.source_first_name,
            visit.source_last_name,
        )
        if value is not None
        and str(value).strip()
    ]
    value = " ".join(parts).strip()
    return value or None


def _serialize_unique_row(row) -> dict:
    return {
        "member_pin": row.member_pin,
        "visits": int(row.visits or 0),
        "first_entered_at": _format_datetime(
            row.first_entered_at
        ),
        "last_entered_at": _format_datetime(
            row.last_entered_at
        ),
        "branches_count": int(
            row.branches_count or 0
        ),
    }


def _serialize_interval_row(row) -> dict:
    interval, branch_name = row
    return {
        "business_date": _format_date(
            interval.business_date
        ),
        "branch_name": str(branch_name),
        "bucket_time": _format_minute(
            int(interval.bucket_minute)
        ),
        "occupancy": int(
            interval.occupancy
        ),
        "entries": int(interval.entries),
        "exits": int(interval.exits),
        "attendance_type": (
            interval.attendance_type
        ),
    }


def _resolve_age_bucket(
    value: str | None,
) -> tuple[int, int]:
    normalized = str(value or "").strip()
    for label, minimum, maximum in AGE_BUCKETS:
        if normalized == label:
            return minimum, maximum

    raise SportsAnalysisValidationError(
        "age_bucket inválido."
    )


def _format_date(value) -> str | None:
    if value is None:
        return None
    return value.strftime("%d/%m/%Y")


def _format_datetime(value) -> str | None:
    if value is None:
        return None
    return (
        value.astimezone(DETAIL_TIMEZONE)
        .strftime("%d/%m/%Y %H:%M:%S")
    )


def _format_minute(
    minute: int,
) -> str:
    hour = minute // 60
    minutes = minute % 60
    return (
        f"{hour:02d}:"
        f"{minutes:02d}"
    )


def _normalize_metric(value: str) -> str:
    return str(value or "").strip().lower()


def _validate_metric(
    metric: str,
) -> None:
    if metric not in _SUPPORTED_METRICS:
        raise SportsAnalysisValidationError(
            "El detalle solicitado no está disponible."
        )


def _normalize_sort_by(
    value: str | None,
    sorts: dict,
    *,
    default: str,
) -> str:
    normalized = str(
        value or default
    ).strip()
    if normalized not in sorts:
        raise SportsAnalysisValidationError(
            "sort_by inválido para el detalle."
        )
    return normalized


def _normalize_sort_dir(
    value: str | None,
    *,
    default: str,
) -> str:
    normalized = str(
        value or default
    ).strip().lower()
    if normalized not in {
        "asc",
        "desc",
    }:
        raise SportsAnalysisValidationError(
            "sort_dir debe ser asc o desc."
        )
    return normalized


def _parse_positive_int(
    value: object,
    name: str,
    *,
    default: int,
) -> int:
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise SportsAnalysisValidationError(
            f"{name} inválido."
        ) from exc

    if parsed <= 0:
        raise SportsAnalysisValidationError(
            f"{name} inválido."
        )
    return parsed
