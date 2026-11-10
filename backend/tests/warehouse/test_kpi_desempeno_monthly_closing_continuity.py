"""Cierre mensual: crecimiento entre cierres canónicos y conciliación con base Gasca."""

from datetime import date
from types import SimpleNamespace

import app.warehouse.services.kpi_desempeno_query_service as query


def _row(row_id, name, inicio, cierre, nuevos=0, reactivaciones=0, bajas=0):
    return SimpleNamespace(
        id=row_id,
        sucursal=name,
        socios_activos_inicio_mes=inicio,
        socios_activos_del_mes=cierre,
        clientes_nuevo_real=nuevos,
        reactivaciones=reactivaciones,
        bajas=bajas,
    )


def _snapshot(snapshot_id, business_date, count):
    return SimpleNamespace(
        id=snapshot_id,
        business_date=business_date,
        captured_at=None,
        row_count_valid=count,
        row_count_rejected=0,
    )


def _install_sources(monkeypatch, *, previous_rows, current_rows, with_previous=True):
    snapshots = {
        (2026, 10): _snapshot(4592, date(2026, 10, 31), len(current_rows)),
        (2026, 9): (
            _snapshot(4500, date(2026, 9, 30), len(previous_rows))
            if with_previous else None
        ),
    }
    rows = {4592: current_rows, 4500: previous_rows}
    monkeypatch.setattr(
        query, "_resolve_last_canonical_snapshot_for_month",
        lambda *, year, month: snapshots.get((year, month)),
    )
    monkeypatch.setattr(
        query, "_fetch_snapshot_rows",
        lambda *, snapshot_id: rows[snapshot_id],
    )
    monkeypatch.setattr(
        query, "_resolve_rows_branch_canon",
        lambda *, rows: (
            {row.id: row.sucursal.replace(" ", "_") for row in rows},
            [],
        ),
    )
    monkeypatch.setattr(
        query, "_fetch_branch_catalog_by_canon",
        lambda *, sucursales_canon: {},
    )


def _current_rows():
    return [
        _row(1, "VILLA VERDE", 1250, 1220, 61, 120, 211),
        _row(2, "VILLAS DEL REY", 1209, 1180, 55, 160, 244),
    ]


def test_october_monthly_growth_uses_september_closes_not_gasca_start(monkeypatch):
    _install_sources(
        monkeypatch,
        previous_rows=[
            _row(3, "VILLA VERDE", 1100, 1210),
            _row(4, "VILLAS DEL REY", 1100, 1166),
        ],
        current_rows=_current_rows(),
    )

    result = query.build_monthly_closing_section(target_month="2026-10")
    by_branch = {row["branch"]["sucursal_canon"]: row for row in result["data"]}

    villa = by_branch["VILLA_VERDE"]["metrics"]
    assert villa["socios_activos_cierre_mes_anterior"] == 1210
    assert villa["crecimiento_inter_mensual"] == 10
    assert villa["crecimiento_real"] == -30
    assert villa["diferencia_bases"] == 40
    assert villa["ajuste_no_explicado"] == 0

    villas = by_branch["VILLAS_DEL_REY"]["metrics"]
    assert villas["socios_activos_cierre_mes_anterior"] == 1166
    assert villas["crecimiento_inter_mensual"] == 14
    assert villas["crecimiento_real"] == -29
    assert villas["diferencia_bases"] == 43
    assert villas["ajuste_no_explicado"] == 0

    assert result["target_month"] == "2026-10"
    assert result["previous_month"] == "2026-09"
    assert result["resolved_snapshot"]["business_date"] == "2026-10-31"
    assert result["previous_resolved_snapshot"]["business_date"] == "2026-09-30"
    assert result["title"] == "Crecimiento mensual de socios por sucursal"


def test_missing_prior_snapshot_does_not_invent_zero_growth(monkeypatch):
    _install_sources(
        monkeypatch, previous_rows=[], current_rows=_current_rows(),
        with_previous=False,
    )

    result = query.build_monthly_closing_section(target_month="2026-10")
    assert result["previous_resolved_snapshot"] is None
    assert all(
        row["metrics"]["crecimiento_inter_mensual"] is None
        and row["metrics"]["socios_activos_cierre_mes_anterior"] is None
        and row["metrics"]["diferencia_bases"] is None
        for row in result["data"]
    )
    assert any(
        warning["code"] == "missing_previous_month_canonical_snapshot"
        for warning in result["warnings"]
    )


def test_missing_branch_prior_month_preserves_other_branches(monkeypatch):
    _install_sources(
        monkeypatch,
        previous_rows=[_row(3, "VILLA VERDE", 1100, 1210)],
        current_rows=_current_rows(),
    )

    result = query.build_monthly_closing_section(target_month="2026-10")
    by_branch = {row["branch"]["sucursal_canon"]: row for row in result["data"]}
    assert by_branch["VILLA_VERDE"]["metrics"]["crecimiento_inter_mensual"] == 10
    assert by_branch["VILLAS_DEL_REY"]["metrics"]["crecimiento_inter_mensual"] is None
    assert any(
        warning["code"] == "missing_previous_month_branch"
        and warning["sucursal_canon"] == "VILLAS_DEL_REY"
        for warning in result["warnings"]
    )
