from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

import app.warehouse.services.track_source_ingresos_daily_service as service


class _FakeColumn:
    def asc(self):
        return self


class _FakeRowsQuery:
    def __init__(self, rows):
        self._rows = list(rows)
        self.snapshot_id = None

    def filter_by(self, **kwargs):
        self.snapshot_id = kwargs.get("snapshot_id")
        return self

    def order_by(self, *_args):
        return self

    def all(self):
        return list(self._rows)


def test_base_ingresos_uses_activo_facturado_and_keeps_negatives(
    monkeypatch: pytest.MonkeyPatch,
):
    snapshot = SimpleNamespace(
        id=101,
        report_type_key="venta_total",
    )
    rows_query = _FakeRowsQuery(
        [
            SimpleNamespace(
                sucursal="SUCURSAL A",
                estatus=" activo ",
                total=Decimal("100.00"),
            ),
            SimpleNamespace(
                sucursal="SUCURSAL A",
                estatus="FACTURADO",
                total=Decimal("-25.00"),
            ),
            SimpleNamespace(
                sucursal="SUCURSAL A",
                estatus="CANCELADO",
                total=Decimal("999.00"),
            ),
            SimpleNamespace(
                sucursal="BECA",
                estatus="ACTIVO",
                total=Decimal("50.00"),
            ),
        ]
    )

    monkeypatch.setattr(
        service,
        "_resolve_venta_total_snapshot_for_track",
        lambda **_kwargs: snapshot,
    )
    monkeypatch.setattr(
        service,
        "VentaTotalSnapshotRowORM",
        SimpleNamespace(
            query=rows_query,
            id=_FakeColumn(),
        ),
    )
    monkeypatch.setattr(
        service,
        "resolve_track_branch_alias",
        lambda **kwargs: (
            "SUCURSAL_A"
            if kwargs["raw_branch_name"] == "SUCURSAL A"
            else None
        ),
    )

    result, snapshot_id, report_type_key = (
        service._build_base_ingresos_map_for_date(
            business_date=date(2026, 7, 31),
            generation_mode="official_closed_day",
        )
    )

    assert rows_query.snapshot_id == 101
    assert snapshot_id == 101
    assert report_type_key == "venta_total"
    assert result == {
        "SUCURSAL_A": {
            "ingreso_real_base_mtd": Decimal("75.00"),
            "source_snapshot_id": 101,
            "source_report_type_key": "venta_total",
        }
    }


def test_merge_propagates_venta_total_lineage_to_aggregator_only_branch():
    rows = service._merge_base_and_agregadoras_maps_for_date(
        business_date=date(2026, 7, 31),
        base_map={},
        agregadoras_map={
            "SUCURSAL_B": {
                "ingreso_wellhub_mtd": Decimal("30.00"),
                "ingreso_totalpass_mtd": Decimal("20.00"),
                "ingreso_real_agregadora_mtd": Decimal("50.00"),
                "source_business_date_agregadoras": date(2026, 7, 31),
                "source_snapshot_id_wellhub": 201,
                "source_snapshot_id_totalpass": 301,
                "source_report_type_key_wellhub": "ingresos_wellhub",
                "source_report_type_key_totalpass": "ingresos_totalpass",
            }
        },
        base_snapshot_id=101,
        base_report_type_key="venta_total",
    )

    assert rows == [
        {
            "business_date": "2026-07-31",
            "sucursal_canon": "SUCURSAL_B",
            "ingreso_real_base_mtd": Decimal("0.00"),
            "ingreso_wellhub_mtd": Decimal("30.00"),
            "ingreso_totalpass_mtd": Decimal("20.00"),
            "ingreso_real_agregadora_mtd": Decimal("50.00"),
            "ingreso_real_total_mtd": Decimal("50.00"),
            "ingreso_real_mtd": Decimal("50.00"),
            "source_snapshot_id": 101,
            "source_report_type_key": "venta_total",
            "source_snapshot_id_reporte_direccion": None,
            "source_snapshot_id_wellhub": 201,
            "source_snapshot_id_totalpass": 301,
            "source_business_date_agregadoras": date(2026, 7, 31),
            "source_report_type_key_reporte_direccion": None,
            "source_report_type_key_wellhub": "ingresos_wellhub",
            "source_report_type_key_totalpass": "ingresos_totalpass",
        }
    ]


class _FakeSnapshotQuery:
    def __init__(self, snapshot):
        self._snapshot = snapshot
        self.filters = {}

    def filter_by(self, **kwargs):
        self.filters = dict(kwargs)
        return self

    def first(self):
        return self._snapshot


def test_explicit_venta_total_snapshot_can_be_non_canonical(
    monkeypatch: pytest.MonkeyPatch,
):
    target_date = date(2026, 7, 31)

    snapshot = SimpleNamespace(
        id=777,
        report_type_key="venta_total",
        is_canonical=False,
    )

    snapshot_query = _FakeSnapshotQuery(snapshot)

    rows_query = _FakeRowsQuery(
        [
            SimpleNamespace(
                sucursal="SUCURSAL A",
                estatus="ACTIVO",
                total=Decimal("125.00"),
            ),
        ]
    )

    monkeypatch.setattr(
        service,
        "VentaTotalSnapshotORM",
        SimpleNamespace(
            query=snapshot_query,
        ),
    )

    monkeypatch.setattr(
        service,
        "VentaTotalSnapshotRowORM",
        SimpleNamespace(
            query=rows_query,
            id=_FakeColumn(),
        ),
    )

    monkeypatch.setattr(
        service,
        "resolve_track_branch_alias",
        lambda **kwargs: (
            "SUCURSAL_A"
            if kwargs["raw_branch_name"] == "SUCURSAL A"
            else None
        ),
    )

    result, snapshot_id, report_type_key = (
        service._build_base_ingresos_map_for_date(
            business_date=target_date,
            generation_mode="official_closed_day",
            venta_total_snapshot_id=777,
        )
    )

    assert snapshot_query.filters == {
        "id": 777,
        "business_date": target_date,
        "snapshot_kind": "daily",
    }

    assert "is_canonical" not in snapshot_query.filters

    assert rows_query.snapshot_id == 777
    assert snapshot_id == 777
    assert report_type_key == "venta_total"

    assert result == {
        "SUCURSAL_A": {
            "ingreso_real_base_mtd": Decimal("125.00"),
            "source_snapshot_id": 777,
            "source_report_type_key": "venta_total",
        }
    }
