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
) -> health._EligibleMember:
    return health._EligibleMember(
        id_socio=id_socio,
        pin=f"PIN-{id_socio}",
        name=name or f"Socio {id_socio}",
        branch_id=branch_id,
        branch_name=branch_name,
        member_since=date(2026, 1, 1),
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
