from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import app.warehouse.services.track_tienda_composition_service as service


class _FakeQuery:
    def __init__(self, rows):
        self._rows = list(rows)
        self.filters = {}

    def filter_by(self, **kwargs):
        self.filters = dict(kwargs)
        return self

    def all(self):
        return list(self._rows)


def _venta_row(
    *,
    row_index: int,
    clave_producto: str,
    descripcion: str,
    total: str,
):
    return SimpleNamespace(
        row_index=row_index,
        fecha="2026-09-14",
        hora="10:00",
        sucursal="VILLAS DEL REY",
        folio=f"F-{row_index}",
        clave=f"C-{row_index}",
        clave_producto=clave_producto,
        descripcion=descripcion,
        cantidad=Decimal("1"),
        precio_unitario=Decimal(total),
        total=Decimal(total),
        forma_pago="EFECTIVO",
        estatus="ACTIVO",
        realizo_venta="ASESOR",
        capturista="CAPTURISTA",
        socio="SOCIO",
    )


def test_composition_reconciles_track_and_keeps_locker_even_with_promo_terms(
    monkeypatch,
):
    resolved_version = SimpleNamespace(
        id=123,
        version_type="cierre_canonico",
        status="success",
        generated_at_utc=None,
        finished_at_utc=None,
    )

    mart_query = _FakeQuery(
        [
            SimpleNamespace(
                source_snapshot_id_tienda=77,
                venta_tienda_real_mtd=Decimal("649.00"),
                meta_venta_tienda_mes=Decimal("1000.00"),
            )
        ]
    )

    source_query = _FakeQuery(
        [
            _venta_row(
                row_index=1,
                clave_producto="LOCKER",
                descripcion="RENTA TRIMESTRAL PROMO $549",
                total="549.00",
            ),
            _venta_row(
                row_index=2,
                clave_producto="BEBIDA",
                descripcion="AGUA",
                total="100.00",
            ),
            _venta_row(
                row_index=3,
                clave_producto="MEMBRESIA",
                descripcion="MENSUALIDAD",
                total="499.00",
            ),
        ]
    )

    monkeypatch.setattr(
        service,
        "resolve_effective_track_daily_version",
        lambda **_kwargs: resolved_version,
    )
    monkeypatch.setattr(
        service,
        "TrackDailyMartORM",
        SimpleNamespace(query=mart_query),
    )
    monkeypatch.setattr(
        service,
        "VentaTotalSnapshotRowORM",
        SimpleNamespace(query=source_query),
    )
    monkeypatch.setattr(
        service,
        "resolve_track_branch_alias",
        lambda **_kwargs: "VILLAS_DEL_REY",
    )

    result = service.build_track_tienda_composition(
        track_date=date(2026, 9, 14),
        generation_mode="official_closed_day",
    )

    assert mart_query.filters == {"track_daily_version_id": 123}
    assert source_query.filters == {"snapshot_id": 77}
    assert result["summary"]["track_total"] == 649.0
    assert result["summary"]["composition_total"] == 649.0
    assert result["summary"]["difference"] == 0.0
    assert result["summary"]["is_reconciled"] is True
    assert result["summary"]["operaciones"] == 2

    composition = {
        item["clave_producto"]: item["total"]
        for item in result["composition"]
    }

    assert composition == {
        "LOCKER": 549.0,
        "BEBIDA": 100.0,
    }
