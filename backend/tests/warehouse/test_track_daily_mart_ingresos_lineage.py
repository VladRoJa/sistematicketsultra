from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

import app.warehouse.services.track_daily_mart_service as service


class _FakeColumn:
    def asc(self):
        return self


class _FakeQuery:
    def __init__(self, rows):
        self._rows = list(rows)
        self.filters = []

    def filter_by(self, **kwargs):
        self.filters.append(kwargs)
        return self

    def order_by(self, *_args):
        return self

    def all(self):
        return list(self._rows)


def _fake_model(
    rows,
    *,
    with_display_order=False,
):
    values = {
        "query": _FakeQuery(rows),
    }

    if with_display_order:
        values["display_order"] = _FakeColumn()

    return SimpleNamespace(**values)


def test_mart_uses_generic_ingresos_snapshot_lineage(
    monkeypatch: pytest.MonkeyPatch,
):
    business_date = date(2026, 7, 31)

    active_branch = SimpleNamespace(
        sucursal_canon="SUCURSAL_A",
    )

    ingresos_row = SimpleNamespace(
        sucursal_canon="SUCURSAL_A",
        business_date=business_date,
        ingreso_real_base_mtd=Decimal("1000.00"),
        ingreso_real_agregadora_mtd=Decimal("250.00"),
        ingreso_real_total_mtd=Decimal("1250.00"),
        ingreso_real_mtd=Decimal("1250.00"),
        source_business_date_agregadoras=business_date,
        source_snapshot_id=501,
        source_snapshot_id_reporte_direccion=999,
    )

    monkeypatch.setattr(
        service,
        "TrackBranchCatalogORM",
        _fake_model(
            [active_branch],
            with_display_order=True,
        ),
    )
    monkeypatch.setattr(
        service,
        "TrackMonthlyTargetORM",
        _fake_model([]),
    )
    monkeypatch.setattr(
        service,
        "TrackSourceDesempenoDailyORM",
        _fake_model([]),
    )
    monkeypatch.setattr(
        service,
        "TrackSourceIngresosDailyORM",
        _fake_model([ingresos_row]),
    )
    monkeypatch.setattr(
        service,
        "TrackSourceNuevosDailyORM",
        _fake_model([]),
    )
    monkeypatch.setattr(
        service,
        "TrackSourceDomiciliadosEfectivosDailyORM",
        _fake_model([]),
    )
    monkeypatch.setattr(
        service,
        "TrackSourceTiendaDailyORM",
        _fake_model([]),
    )

    rows = service.build_track_daily_mart_for_date(
        business_date=business_date,
        generation_mode="official_closed_day",
    )

    assert len(rows) == 1

    row = rows[0]

    assert row["sucursal_canon"] == "SUCURSAL_A"
    assert row["ingreso_real_base_mtd"] == Decimal("1000.00")
    assert row["ingreso_real_agregadora_mtd"] == Decimal("250.00")
    assert row["ingreso_real_total_mtd"] == Decimal("1250.00")
    assert row["ingreso_real_mtd"] == Decimal("1250.00")

    assert row["source_snapshot_id_ingresos"] == 501
    assert row["source_snapshot_id_ingresos"] != 999
