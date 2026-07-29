from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

import app.warehouse.services.venta_total_repository as repository


def _parsed_row(*, telefono: object = "TEL-SINTETICO-001") -> dict[str, object]:
    return {
        "row_index": 0,
        "fecha": "2026-07-28",
        "sucursal": "SUCURSAL SINTETICA",
        "folio": "FOLIO-SINTETICO-001",
        "clave": "CLAVE-SINTETICA",
        "clave_producto": "PRODUCTO-SINTETICO",
        "descripcion": "DESCRIPCION SINTETICA",
        "cantidad": Decimal("1"),
        "precio_unitario": Decimal("100.00"),
        "subtotal": Decimal("100.00"),
        "iva_importe": Decimal("16.00"),
        "iva_tasa": Decimal("0.16"),
        "total": Decimal("116.00"),
        "forma_pago": "EFECTIVO",
        "estatus": "PAGADO",
        "motivo": None,
        "realizo_venta": "VENDEDOR SINTETICO",
        "hora": "10:30",
        "id_orden": "ORDEN-SINTETICA",
        "encuesta": None,
        "capturista": "CAPTURISTA SINTETICO",
        "pin": "PIN-SINTETICO",
        "socio": "SOCIO-SINTETICO",
        "nuevo": "NO",
        "tipo": "VENTA",
        "telefono": telefono,
    }


class _FakeSession:
    def __init__(self) -> None:
        self.added_rows = []
        self.flush_calls = 0

    def add_all(self, rows) -> None:
        self.added_rows.extend(rows)

    def flush(self) -> None:
        self.flush_calls += 1


def test_repository_normalizes_optional_telefono():
    normalized_rows = repository._rows_from_parsed_snapshot(
        {
            "rows": [
                _parsed_row(telefono="  TEL-SINTETICO-ESPACIOS  "),
                {
                    key: value
                    for key, value in _parsed_row().items()
                    if key != "telefono"
                },
            ]
        }
    )

    assert normalized_rows[0]["telefono"] == "TEL-SINTETICO-ESPACIOS"
    assert normalized_rows[1]["telefono"] is None


def test_insert_snapshot_rows_persists_telefono(
    monkeypatch: pytest.MonkeyPatch,
):
    fake_session = _FakeSession()
    monkeypatch.setattr(
        repository,
        "db",
        SimpleNamespace(session=fake_session),
    )

    normalized_rows = repository._rows_from_parsed_snapshot(
        {"rows": [_parsed_row()]}
    )

    inserted_count = repository._insert_snapshot_rows(
        snapshot_id=91,
        rows=normalized_rows,
    )

    assert inserted_count == 1
    assert fake_session.flush_calls == 1
    assert fake_session.added_rows[0].telefono == "TEL-SINTETICO-001"
