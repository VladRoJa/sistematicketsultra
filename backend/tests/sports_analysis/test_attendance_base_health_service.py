from datetime import date

import pytest

from app.sports_analysis import (
    attendance_base_health_service as health,
)
from app.sports_analysis.attendance_access import (
    SportsAnalysisScope,
)
from app.sports_analysis.attendance_query_service import (
    SportsAnalysisValidationError,
)


def _scope() -> SportsAnalysisScope:
    return SportsAnalysisScope(
        role="ADMINISTRADOR",
        is_global=True,
        allowed_branch_ids=(1, 2, 3),
        fixed_branch_id=None,
    )


def _member(
    id_socio: str,
    *,
    branch_id: int = 1,
    branch_name: str = "Sucursal Uno",
    name: str | None = None,
    member_since: date | None = date(2026, 1, 1),
    expiration_date: date = date(2026, 12, 31),
) -> health._EligibleMember:
    return health._EligibleMember(
        id_socio=id_socio,
        pin=f"PIN-{id_socio}",
        name=name or f"Socio {id_socio}",
        branch_id=branch_id,
        branch_name=branch_name,
        member_since=member_since,
        expiration_date=expiration_date,
        snapshot_date=date(2026, 9, 25),
    )


def _state() -> health._BaseHealthState:
    return health._BaseHealthState(
        eligible_members={
            "100": _member("100"),
            "200": _member(
                "200",
                branch_id=2,
                branch_name="Sucursal Dos",
            ),
            "300": _member("300"),
            "400": _member("400"),
        },
        visited_member_ids=frozenset(
            {"100", "300", "999"}
        ),
        snapshot_dates=(
            date(2026, 9, 1),
            date(2026, 9, 25),
        ),
        total_visits_checked=100,
        resolved_visits=96,
    )


def test_base_health_utilization_uses_eligible_members(
    monkeypatch,
):
    monkeypatch.setattr(
        health,
        "_build_state",
        lambda *_args, **_kwargs: (
            _state(),
            (1, 2),
        ),
    )

    result = health.attendance_base_health(
        _scope(),
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 25),
        branch_id=None,
        region_key=None,
    )

    assert result["summary"] == {
        "eligible_members": 4,
        "members_with_visit": 2,
        "members_without_visit": 2,
        "utilization_pct": 50.0,
        "without_visit_pct": 50.0,
        "frequency_avg_per_week": 0.0,
        "frequency_median_per_week": 0.0,
    }
    assert (
        result["source"]["identity_coverage_pct"]
        == 96.0
    )
    assert result["source"]["snapshot_count"] == 2
    assert (
        result["filters"]["attendance_type"]
        == "SOCIO"
    )


def test_base_health_ignores_resolved_visits_outside_base(
    monkeypatch,
):
    state = _state()
    monkeypatch.setattr(
        health,
        "_build_state",
        lambda *_args, **_kwargs: (
            state,
            (1, 2),
        ),
    )

    result = health.attendance_base_health(
        _scope(),
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 25),
        branch_id=1,
        region_key=None,
    )

    assert result["summary"]["members_with_visit"] == 2
    assert result["summary"]["eligible_members"] == 4


def test_base_health_empty_source_is_safe(
    monkeypatch,
):
    empty = health._BaseHealthState(
        eligible_members={},
        visited_member_ids=frozenset(),
        snapshot_dates=(),
        total_visits_checked=0,
        resolved_visits=0,
    )
    monkeypatch.setattr(
        health,
        "_build_state",
        lambda *_args, **_kwargs: (
            empty,
            (1,),
        ),
    )

    result = health.attendance_base_health(
        _scope(),
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 25),
        branch_id=1,
        region_key=None,
    )

    assert result["summary"]["eligible_members"] == 0
    assert result["summary"]["utilization_pct"] == 0.0
    assert result["source"]["available"] is False


def test_member_detail_splits_with_and_without_visit(
    monkeypatch,
):
    monkeypatch.setattr(
        health,
        "_build_state",
        lambda *_args, **_kwargs: (
            _state(),
            (1, 2),
        ),
    )

    with_visit = (
        health.attendance_base_health_members(
            _scope(),
            date_from=date(2026, 9, 1),
            date_to=date(2026, 9, 25),
            branch_id=None,
            region_key=None,
            status="WITH_VISIT",
            page=1,
            page_size=50,
        )
    )
    without_visit = (
        health.attendance_base_health_members(
            _scope(),
            date_from=date(2026, 9, 1),
            date_to=date(2026, 9, 25),
            branch_id=None,
            region_key=None,
            status="WITHOUT_VISIT",
            page=1,
            page_size=50,
        )
    )

    assert with_visit["count"] == 2
    assert {
        row["id_socio"]
        for row in with_visit["rows"]
    } == {"100", "300"}
    assert all(
        row["has_visit"] is True
        for row in with_visit["rows"]
    )

    assert without_visit["count"] == 2
    assert {
        row["id_socio"]
        for row in without_visit["rows"]
    } == {"200", "400"}
    assert all(
        row["has_visit"] is False
        for row in without_visit["rows"]
    )


def test_member_detail_rejects_unknown_status(
    monkeypatch,
):
    monkeypatch.setattr(
        health,
        "_build_state",
        lambda *_args, **_kwargs: (
            _state(),
            (1,),
        ),
    )

    with pytest.raises(
        SportsAnalysisValidationError
    ):
        health.attendance_base_health_members(
            _scope(),
            date_from=date(2026, 9, 1),
            date_to=date(2026, 9, 25),
            branch_id=None,
            region_key=None,
            status="ALL",
        )


def test_record_member_visits_accumulates_count_and_dates():
    stats: dict[str, health._MemberVisitStats] = {}

    health._record_member_visits(
        stats,
        id_socio="100",
        visit_count=2,
        business_date=date(2026, 9, 10),
    )
    health._record_member_visits(
        stats,
        id_socio="100",
        visit_count=3,
        business_date=date(2026, 9, 5),
    )
    health._record_member_visits(
        stats,
        id_socio="100",
        visit_count=1,
        business_date=date(2026, 9, 20),
    )

    assert stats["100"] == health._MemberVisitStats(
        visit_count=6,
        first_visit_date=date(2026, 9, 5),
        last_visit_date=date(2026, 9, 20),
    )


def test_frequency_uses_real_eligible_days():
    member = _member(
        "100",
        member_since=date(2026, 9, 15),
        expiration_date=date(2026, 9, 21),
    )

    days = health._member_eligible_days(
        member,
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 30),
    )

    frequency = health._member_weekly_frequency(
        member,
        health._MemberVisitStats(
            visit_count=2,
            first_visit_date=date(2026, 9, 15),
            last_visit_date=date(2026, 9, 20),
        ),
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 30),
    )

    assert days == 7
    assert frequency == 2.0


def test_frequency_metrics_include_zero_and_partial_members():
    state = health._BaseHealthState(
        eligible_members={
            "100": _member(
                "100",
                member_since=date(2026, 9, 1),
                expiration_date=date(2026, 9, 7),
            ),
            "200": _member(
                "200",
                member_since=date(2026, 9, 1),
                expiration_date=date(2026, 9, 14),
            ),
            "300": _member(
                "300",
                member_since=date(2026, 9, 1),
                expiration_date=date(2026, 9, 7),
            ),
        },
        visited_member_ids=frozenset({"100", "200"}),
        snapshot_dates=(date(2026, 9, 1),),
        total_visits_checked=4,
        resolved_visits=4,
        member_visit_stats={
            "100": health._MemberVisitStats(
                visit_count=2,
                first_visit_date=date(2026, 9, 1),
                last_visit_date=date(2026, 9, 5),
            ),
            "200": health._MemberVisitStats(
                visit_count=1,
                first_visit_date=date(2026, 9, 2),
                last_visit_date=date(2026, 9, 2),
            ),
        },
    )

    metrics = health._frequency_metrics(
        state,
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 30),
    )

    assert metrics["average_per_week"] == 0.83
    assert metrics["median_per_week"] == 0.5
    assert [
        row["count"]
        for row in metrics["distribution"]
    ] == [1, 1, 0, 1, 0]
