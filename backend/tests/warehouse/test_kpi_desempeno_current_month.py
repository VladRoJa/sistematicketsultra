"""Current month is an opt-in observation, never a historical close."""
from datetime import date, datetime, timezone
from types import SimpleNamespace

import app.warehouse.services.kpi_desempeno_query_service as query


def _snapshot(snapshot_id, day):
    return SimpleNamespace(
        id=snapshot_id,
        business_date=day,
        captured_at=datetime(day.year, day.month, day.day, 18, tzinfo=timezone.utc),
        report_type_key="kpi_desempeno",
        snapshot_kind="daily",
        is_canonical=True,
    )


def _install(monkeypatch, *, today, current_rows, closed_day, current_exists=True):
    closed = _snapshot(1, closed_day)
    current = _snapshot(2, today)
    lookup = {"A": query.TRACK_BRANCH_COHORT_LEGACY_21, "B": query.TRACK_BRANCH_COHORT_NEW_GYMS}
    history = [SimpleNamespace(id=1, sucursal="A", socios_activos_del_mes=100),
               SimpleNamespace(id=2, sucursal="B", socios_activos_del_mes=50)]
    rows = {1: history, 2: [
        SimpleNamespace(id=index, sucursal=canon, socios_activos_del_mes=value)
        for index, (canon, value) in enumerate(current_rows, 10)
    ]}
    calls = []
    monkeypatch.setattr(query, "_resolve_last_canonical_snapshot_for_month",
                        lambda *, year, month: closed if (year, month) == (closed_day.year, closed_day.month) else None)

    def current_resolver(*, start_date, end_date):
        calls.append((start_date, end_date))
        return current if current_exists else None

    monkeypatch.setattr(query, "_resolve_last_canonical_snapshot_for_date_range", current_resolver)
    monkeypatch.setattr(query, "_fetch_snapshot_rows", lambda *, snapshot_id: rows[snapshot_id])
    monkeypatch.setattr(query, "_resolve_rows_branch_canon",
                        lambda *, rows: ({row.id: row.sucursal for row in rows}, []))
    monkeypatch.setattr(query, "_fetch_branch_catalog_by_canon", lambda **kwargs: {})
    monkeypatch.setattr(query, "build_track_branch_cohort_lookup",
                        lambda **kwargs: {key: value for key, value in lookup.items()
                                          if kwargs.get("sucursales_canon") is None or key in kwargs["sucursales_canon"]})
    return calls


def _point(report, canon, year, month):
    row = next(row for row in report["data"] if row["branch"]["sucursal_canon"] == canon)
    series = next(series for series in row["series"] if series["year"] == year)
    return series["months"][month - 1]


def test_current_month_is_provisional_and_historical_unchanged(monkeypatch):
    calls = _install(monkeypatch, today=date(2026, 11, 25),
                     closed_day=date(2026, 10, 31), current_rows=[("A", 108), ("B", 0)])
    report = query.build_monthly_branch_year_overlay_section(
        start_year=2026, end_month="2026-10", current_business_date=date(2026, 11, 25))
    assert calls == [(date(2026, 11, 1), date(2026, 11, 25))]
    assert report["end_month"] == "2026-10"
    assert report["current_month"] == "2026-11"
    assert report["current_snapshot"]["snapshot_id"] == 2
    assert _point(report, "A", 2026, 10)["socios_activos_cierre_mes"] == 100
    assert not _point(report, "A", 2026, 10).get("is_provisional")
    assert _point(report, "A", 2026, 11)["is_provisional"] is True
    assert _point(report, "A", 2026, 11)["source"]["captured_at"].startswith("2026-11-25")
    assert _point(report, "B", 2026, 11)["socios_activos_cierre_mes"] == 0
    assert _point(report, "TOTAL_ULTRA", 2026, 11)["socios_activos_cierre_mes"] == 108
    assert _point(report, "TOTAL_ULTRA", 2026, 11)["is_provisional"]
    assert _point(report, "A", 2026, 12)["socios_activos_cierre_mes"] is None


def test_incomplete_current_cohort_is_not_a_false_total(monkeypatch):
    _install(monkeypatch, today=date(2026, 11, 25),
             closed_day=date(2026, 10, 31), current_rows=[("A", 108)])
    report = query.build_monthly_branch_year_overlay_section(
        start_year=2026, end_month="2026-10", current_business_date=date(2026, 11, 25))
    assert _point(report, "A", 2026, 11)["socios_activos_cierre_mes"] == 108
    assert _point(report, "B", 2026, 11)["socios_activos_cierre_mes"] is None
    assert _point(report, "TOTAL_ULTRA", 2026, 11)["socios_activos_cierre_mes"] is None
    assert any(w["code"] == "incomplete_current_month_cohort" for w in report["warnings"])


def test_missing_cut_and_historical_opt_out(monkeypatch):
    calls = _install(monkeypatch, today=date(2026, 11, 25),
                     closed_day=date(2026, 10, 31), current_rows=[], current_exists=False)
    old = query.build_monthly_branch_year_overlay_section(start_year=2026, end_month="2026-10")
    assert old["current_month"] is None
    assert calls == []
    report = query.build_monthly_branch_year_overlay_section(
        start_year=2026, end_month="2026-10", current_business_date=date(2026, 11, 25))
    assert report["current_snapshot"] is None
    assert _point(report, "A", 2026, 11)["socios_activos_cierre_mes"] is None


def test_january_rollover_keeps_december_closed(monkeypatch):
    _install(monkeypatch, today=date(2027, 1, 3),
             closed_day=date(2026, 12, 31), current_rows=[("A", 109), ("B", 51)])
    report = query.build_monthly_branch_year_overlay_section(
        start_year=2026, end_month="2026-12", current_business_date=date(2027, 1, 3))
    assert report["years"] == [2026, 2027]
    assert not _point(report, "A", 2026, 12).get("is_provisional")
    assert _point(report, "A", 2027, 1)["is_provisional"] is True
    assert _point(report, "A", 2027, 2)["socios_activos_cierre_mes"] is None


def test_explicit_old_month_does_not_add_current(monkeypatch):
    calls = _install(monkeypatch, today=date(2026, 11, 25),
                     closed_day=date(2026, 9, 30), current_rows=[("A", 108)])
    report = query.build_monthly_branch_year_overlay_section(
        start_year=2026, end_month="2026-09", current_business_date=date(2026, 11, 25))
    assert report["current_month"] is None
    assert calls == []
    assert _point(report, "A", 2026, 11)["socios_activos_cierre_mes"] is None
