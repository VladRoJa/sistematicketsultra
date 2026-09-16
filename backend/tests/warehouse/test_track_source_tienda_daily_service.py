from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import app.warehouse.services.track_source_tienda_daily_service as service


def test_locker_product_key_overrides_description_exclusions():
    locker_row = SimpleNamespace(
        descripcion="RENTA TRIMESTRAL PROMO $549",
        clave_producto="LOCKER",
        total=Decimal("549.00"),
        estatus="ACTIVO",
    )
    non_locker_row = SimpleNamespace(
        descripcion="RENTA TRIMESTRAL PROMO $549",
        clave_producto="OTRO",
        total=Decimal("549.00"),
        estatus="ACTIVO",
    )
    membership_row = SimpleNamespace(
        descripcion="RENTA MENSUAL $499",
        clave_producto="MEMBRESIA",
        total=Decimal("499.00"),
        estatus="ACTIVO",
    )

    assert service._is_tienda_candidate(locker_row) is True
    assert service._is_tienda_candidate(non_locker_row) is False
    assert service._is_tienda_candidate(membership_row) is False
