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


def test_composition_groups_families_and_canonical_products_without_merging_flavors(
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
                venta_tienda_real_mtd=Decimal("909.00"),
                meta_venta_tienda_mes=Decimal("1500.00"),
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
                clave_producto="001",
                descripcion="AGUA E-PURA 1 LITRO",
                total="100.00",
            ),
            _venta_row(
                row_index=3,
                clave_producto="025",
                descripcion="AGUA E-PURA 1LT",
                total="50.00",
            ),
            _venta_row(
                row_index=4,
                clave_producto="101",
                descripcion="GATORADE 1LT PONCHE DE FRUTAS",
                total="80.00",
            ),
            _venta_row(
                row_index=5,
                clave_producto="102",
                descripcion="GATORADE 1 LT PONCHE DE FRUTAS",
                total="70.00",
            ),
            _venta_row(
                row_index=6,
                clave_producto="103",
                descripcion="GATORADE 1LT LIMON",
                total="60.00",
            ),
            _venta_row(
                row_index=7,
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
    assert result["summary"]["track_total"] == 909.0
    assert result["summary"]["composition_total"] == 909.0
    assert result["summary"]["difference"] == 0.0
    assert result["summary"]["is_reconciled"] is True
    assert result["summary"]["operaciones"] == 6

    families = {item["familia"]: item["total"] for item in result["composition"]}
    assert families == {
        "Lockers": 549.0,
        "Aguas": 150.0,
        "Bebidas isotónicas": 210.0,
    }

    products = {
        item["producto_canonico"]: item
        for item in result["products"]
    }

    assert products["AGUA E-PURA 1 L"]["total"] == 150.0
    assert products["AGUA E-PURA 1 L"]["claves_producto"] == ["001", "025"]
    assert products["GATORADE 1 L PONCHE DE FRUTAS"]["total"] == 150.0
    assert products["GATORADE 1 L LIMON"]["total"] == 60.0


def test_canonical_product_filter_returns_all_spelling_variants(monkeypatch):
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
                venta_tienda_real_mtd=Decimal("150.00"),
                meta_venta_tienda_mes=Decimal("500.00"),
            )
        ]
    )

    source_query = _FakeQuery(
        [
            _venta_row(
                row_index=1,
                clave_producto="101",
                descripcion="GATORADE 1LT PONCHE DE FRUTAS",
                total="80.00",
            ),
            _venta_row(
                row_index=2,
                clave_producto="102",
                descripcion="GATORADE 1 LT PONCHE DE FRUTAS",
                total="70.00",
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
        include_operations=True,
        producto_canonico="GATORADE 1 L PONCHE DE FRUTAS",
    )

    assert result["operation_count"] == 2
    assert [item["row_index"] for item in result["operations"]] == [2, 1]


def test_product_family_classification_covers_known_remaining_items():
    assert service._classify_product_family(
        clave_producto="004",
        descripcion="GATORLYTE MORAS 20 OZ",
    ) == "Bebidas isotónicas"
    assert service._classify_product_family(
        clave_producto="031",
        descripcion="BEBIDA ENERGIZANTE GHOST 473 ML",
    ) == "Bebidas energéticas"

    accessory_descriptions = (
        "PLAYERA ULTRA",
        "MORRALITO MESH",
        "MORRALITO ULTRA",
        "SUDADERA ULTRA",
        "GORRA ULTRA",
        "VTA PZA TAPETE YOGA",
        "TRAVEL BAG",
    )

    for description in accessory_descriptions:
        assert service._classify_product_family(
            clave_producto="999",
            descripcion=description,
        ) == "Accesorios"
