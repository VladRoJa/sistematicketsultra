from types import SimpleNamespace

import app.warehouse.services.track_source_domiciliados_efectivos_daily_service as domiciliados_service
from app.warehouse.services.track_source_domiciliados_efectivos_daily_service import (
    _is_countable_domiciliado_status,
)


def test_domiciliado_status_activo_counts():
    assert _is_countable_domiciliado_status("ACTIVO") is True


def test_domiciliado_status_facturado_counts():
    assert _is_countable_domiciliado_status("FACTURADO") is True


def test_domiciliado_status_other_does_not_count():
    assert _is_countable_domiciliado_status("CANCELADO") is False

def test_builder_counts_activo_and_facturado_in_mtd(monkeypatch):
    snapshot = SimpleNamespace(
        id=123,
        report_type_key="venta_total",
    )

    rows = [
        SimpleNamespace(
            row_index=1,
            fecha="17-08-26",
            sucursal="SERRANIA",
            estatus="ACTIVO",
            forma_pago="DOMICILIADO",
        ),
        SimpleNamespace(
            row_index=2,
            fecha="18-08-26",
            sucursal="SERRANIA",
            estatus="FACTURADO",
            forma_pago="DOMICILIADO",
        ),
        SimpleNamespace(
            row_index=3,
            fecha="18-08-26",
            sucursal="SERRANIA",
            estatus="CANCELADO",
            forma_pago="DOMICILIADO",
        ),
    ]

    class FakeQuery:
        def filter_by(self, **kwargs):
            assert kwargs == {"snapshot_id": 123}
            return self

        def order_by(self, *args, **kwargs):
            return self

        def all(self):
            return rows

    monkeypatch.setattr(
        domiciliados_service,
        "_resolve_venta_total_snapshot_for_track_date",
        lambda *, business_date: snapshot,
    )

    class FakeRowIndex:
        @staticmethod
        def asc():
            return None

    class FakeVentaTotalSnapshotRowORM:
        query = FakeQuery()
        row_index = FakeRowIndex()

    monkeypatch.setattr(
        domiciliados_service,
        "VentaTotalSnapshotRowORM",
        FakeVentaTotalSnapshotRowORM,
    )

    monkeypatch.setattr(
        domiciliados_service,
        "resolve_track_branch_alias",
        lambda **kwargs: "SERRANIA",
    )

    result = domiciliados_service.build_track_source_domiciliados_efectivos_daily_for_date(
        business_date="2026-08-18",
    )

    assert result == [
        {
            "business_date": "2026-08-18",
            "sucursal_canon": "SERRANIA",
            "nuevos_domiciliados_real_mtd": 2,
            "source_snapshot_id": 123,
            "source_report_type_key": "venta_total",
        }
    ]
