from __future__ import annotations

from collections import defaultdict
from datetime import date
from statistics import mean, median
from zoneinfo import ZoneInfo

from app.extensions import db
from app.models.attendance import (
    TrackAttendanceDailyMartORM,
    TrackAttendanceIntervalMartORM,
    WarehouseAttendanceVisitORM,
)


TIJUANA_TZ = ZoneInfo("America/Tijuana")
ALL_ATTENDANCE_TYPES = "__ALL__"
BUCKET_MINUTES = 15
BUCKET_COUNT = 24 * 60 // BUCKET_MINUTES


def rebuild_attendance_marts(
    *,
    business_date: date,
    source_run_id: int | None,
) -> None:
    visits = (
        db.session.query(
            WarehouseAttendanceVisitORM
        )
        .filter(
            WarehouseAttendanceVisitORM.business_date
            == business_date,
            WarehouseAttendanceVisitORM.sucursal_id
            .isnot(None),
        )
        .all()
    )

    (
        db.session.query(
            TrackAttendanceIntervalMartORM
        )
        .filter(
            TrackAttendanceIntervalMartORM
            .business_date
            == business_date
        )
        .delete(synchronize_session=False)
    )
    (
        db.session.query(
            TrackAttendanceDailyMartORM
        )
        .filter(
            TrackAttendanceDailyMartORM
            .business_date
            == business_date
        )
        .delete(synchronize_session=False)
    )

    grouped: dict[
        tuple[int, str],
        list[WarehouseAttendanceVisitORM],
    ] = defaultdict(list)

    for visit in visits:
        branch_id = int(visit.sucursal_id)
        attendance_type = str(
            visit.attendance_type or ""
        ).strip().upper()

        if not attendance_type:
            continue

        grouped[
            (branch_id, attendance_type)
        ].append(visit)
        grouped[
            (branch_id, ALL_ATTENDANCE_TYPES)
        ].append(visit)

    for (
        branch_id,
        attendance_type,
    ), group_visits in grouped.items():
        intervals = _build_intervals(
            group_visits,
            business_date=business_date,
        )

        peak_occupancy = max(
            (
                item["occupancy"]
                for item in intervals
            ),
            default=0,
        )
        peak_minute = next(
            (
                item["bucket_minute"]
                for item in intervals
                if item["occupancy"]
                == peak_occupancy
            ),
            None,
        )
        if peak_occupancy == 0:
            peak_minute = None

        for item in intervals:
            db.session.add(
                TrackAttendanceIntervalMartORM(
                    business_date=business_date,
                    sucursal_id=branch_id,
                    attendance_type=(
                        attendance_type
                    ),
                    bucket_minute=item[
                        "bucket_minute"
                    ],
                    entries=item["entries"],
                    exits=item["exits"],
                    occupancy=item["occupancy"],
                    unique_entries=item[
                        "unique_entries"
                    ],
                    source_run_id=source_run_id,
                )
            )

        closed_durations = [
            int(visit.duration_seconds)
            for visit in group_visits
            if (
                visit.visit_status == "CLOSED"
                and visit.duration_seconds
                is not None
            )
        ]

        status_counts: dict[
            str,
            int,
        ] = defaultdict(int)
        for visit in group_visits:
            status_counts[
                str(visit.visit_status)
            ] += 1

        unique_members = len(
            {
                str(visit.member_pin)
                for visit in group_visits
                if visit.member_pin
            }
        )

        db.session.add(
            TrackAttendanceDailyMartORM(
                business_date=business_date,
                sucursal_id=branch_id,
                attendance_type=attendance_type,
                visits=len(group_visits),
                unique_members=unique_members,
                closed_visits=status_counts[
                    "CLOSED"
                ],
                open_visits=status_counts[
                    "OPEN"
                ],
                cross_day_visits=status_counts[
                    "CROSS_DAY"
                ],
                invalid_time_visits=status_counts[
                    "INVALID_TIME"
                ],
                average_duration_seconds=(
                    int(
                        round(
                            mean(
                                closed_durations
                            )
                        )
                    )
                    if closed_durations
                    else None
                ),
                median_duration_seconds=(
                    int(
                        round(
                            median(
                                closed_durations
                            )
                        )
                    )
                    if closed_durations
                    else None
                ),
                peak_occupancy=peak_occupancy,
                peak_minute=peak_minute,
                source_run_id=source_run_id,
            )
        )


def _build_intervals(
    visits: list[WarehouseAttendanceVisitORM],
    *,
    business_date: date,
) -> list[dict]:
    entries = [0] * BUCKET_COUNT
    exits = [0] * BUCKET_COUNT
    unique_entries: list[set[str]] = [
        set() for _ in range(BUCKET_COUNT)
    ]
    occupancy_events: list[
        tuple[float, int]
    ] = []

    for visit in visits:
        entered_local = (
            visit.entered_at_utc.astimezone(
                TIJUANA_TZ
            )
        )
        if entered_local.date() == business_date:
            entry_bucket = _bucket_index(
                entered_local
            )
            entries[entry_bucket] += 1
            if visit.member_pin:
                unique_entries[
                    entry_bucket
                ].add(str(visit.member_pin))

        exited_local = None
        if visit.exited_at_utc is not None:
            exited_local = (
                visit.exited_at_utc.astimezone(
                    TIJUANA_TZ
                )
            )
            if (
                exited_local.date()
                == business_date
            ):
                exits[
                    _bucket_index(
                        exited_local
                    )
                ] += 1

        if (
            visit.visit_status != "CLOSED"
            or exited_local is None
            or entered_local.date()
            != business_date
            or exited_local.date()
            != business_date
        ):
            continue

        occupancy_events.append(
            (
                _seconds_since_midnight(
                    entered_local
                ),
                1,
            )
        )
        occupancy_events.append(
            (
                _seconds_since_midnight(
                    exited_local
                ),
                -1,
            )
        )

    # En empate procesa salida antes de entrada
    # para no crear un pico artificial.
    occupancy_events.sort(
        key=lambda item: (
            item[0],
            item[1],
        )
    )

    interval_peaks = [0] * BUCKET_COUNT
    occupancy = 0
    event_index = 0

    for bucket_index in range(
        BUCKET_COUNT
    ):
        bucket_start_seconds = (
            bucket_index
            * BUCKET_MINUTES
            * 60
        )
        bucket_end_seconds = (
            (bucket_index + 1)
            * BUCKET_MINUTES
            * 60
        )

        # Eventos exactamente en el inicio pertenecen
        # al nuevo intervalo. Aplicarlos antes de medir
        # evita conservar una salida en el bucket siguiente.
        while (
            event_index
            < len(occupancy_events)
            and occupancy_events[
                event_index
            ][0]
            <= bucket_start_seconds
        ):
            _, delta = occupancy_events[
                event_index
            ]
            occupancy = max(
                0,
                occupancy + delta,
            )
            event_index += 1

        peak = occupancy

        while (
            event_index
            < len(occupancy_events)
            and occupancy_events[
                event_index
            ][0]
            < bucket_end_seconds
        ):
            _, delta = occupancy_events[
                event_index
            ]
            occupancy = max(
                0,
                occupancy + delta,
            )
            peak = max(peak, occupancy)
            event_index += 1

        interval_peaks[
            bucket_index
        ] = peak

    return [
        {
            "bucket_minute": (
                bucket_index * BUCKET_MINUTES
            ),
            "entries": entries[
                bucket_index
            ],
            "exits": exits[bucket_index],
            "occupancy": interval_peaks[
                bucket_index
            ],
            "unique_entries": len(
                unique_entries[bucket_index]
            ),
        }
        for bucket_index in range(
            BUCKET_COUNT
        )
    ]


def _bucket_index(value) -> int:
    minute = (
        value.hour * 60
        + value.minute
    )
    return min(
        minute // BUCKET_MINUTES,
        BUCKET_COUNT - 1,
    )


def _seconds_since_midnight(value) -> float:
    return (
        value.hour * 3600
        + value.minute * 60
        + value.second
        + value.microsecond / 1_000_000
    )
