from __future__ import annotations

from datetime import date

import pytest

from app.warehouse.jobs.reactivation_sources_daily_job import run_job


def test_run_job_executes_activos_then_previous_day_vencidos():
    calls = []

    def activos_sync(**kwargs):
        calls.append(("activos", kwargs))
        return {"snapshot_id": 11}

    def vencidos_sync(**kwargs):
        calls.append(("vencidos", kwargs))
        return {"snapshot_id": 22}

    result = run_job(
        business_date=date(2026, 9, 8),
        requested_by="test_runner",
        activos_sync=activos_sync,
        vencidos_sync=vencidos_sync,
    )

    assert [name for name, _ in calls] == ["activos", "vencidos"]
    assert calls[0][1]["business_date"] == date(2026, 9, 8)
    assert calls[1][1]["business_date"] == date(2026, 9, 7)
    assert result["socios_activos_business_date"] == "2026-09-08"
    assert result["socios_vencidos_business_date"] == "2026-09-07"


def test_run_job_fails_closed_before_vencidos_when_activos_fails():
    vencidos_calls = []

    def activos_sync(**_kwargs):
        raise RuntimeError("falló socios activos")

    def vencidos_sync(**kwargs):
        vencidos_calls.append(kwargs)
        return {"snapshot_id": 22}

    with pytest.raises(RuntimeError, match="falló socios activos"):
        run_job(
            business_date=date(2026, 9, 8),
            activos_sync=activos_sync,
            vencidos_sync=vencidos_sync,
        )

    assert vencidos_calls == []


def test_run_job_propagates_vencidos_failure_after_activos_success():
    calls = []

    def activos_sync(**kwargs):
        calls.append(("activos", kwargs))
        return {"snapshot_id": 11}

    def vencidos_sync(**kwargs):
        calls.append(("vencidos", kwargs))
        raise RuntimeError("falló socios vencidos")

    with pytest.raises(RuntimeError, match="falló socios vencidos"):
        run_job(
            business_date=date(2026, 9, 8),
            activos_sync=activos_sync,
            vencidos_sync=vencidos_sync,
        )

    assert [name for name, _ in calls] == ["activos", "vencidos"]


def test_run_job_handles_previous_day_across_year_boundary():
    captured = {}

    def activos_sync(**kwargs):
        captured["activos"] = kwargs["business_date"]
        return {"snapshot_id": 1}

    def vencidos_sync(**kwargs):
        captured["vencidos"] = kwargs["business_date"]
        return {"snapshot_id": 2}

    result = run_job(
        business_date=date(2027, 1, 1),
        activos_sync=activos_sync,
        vencidos_sync=vencidos_sync,
    )

    assert captured["activos"] == date(2027, 1, 1)
    assert captured["vencidos"] == date(2026, 12, 31)
    assert result["socios_vencidos_business_date"] == "2026-12-31"
