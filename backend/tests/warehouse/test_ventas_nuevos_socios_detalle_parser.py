from __future__ import annotations

from io import BytesIO

import pytest
from openpyxl import Workbook

from app.warehouse.services.ventas_nuevos_socios_detalle_parser import (
    EXPECTED_COLUMNS,
    VentasNuevosSociosDetalleLayoutError,
    parse_ventas_nuevos_socios_detalle_xlsx,
)


def _base_row() -> dict[str, object]:
    return {
        "IDSocio": 123456,
        "Pin": 12345,
        "Sucursal": "PASEO 2000",
        "Nombre": "NOMBRE",
        "ApellidoPaterno": "PATERNO",
        "ApellidoMaterno": "MATERNO",
        "Lada": "686",
        "Telefono": "1234567",
        "Domicilio": None,
        "Genero": "Masculino",
        "FechaNacimiento": "01-01-2000",
        "Email": "persona@example.com",
        "FechaCreacion": "01-07-2026 08:00:00",
        "Inscripcion": "Inscripcion $99",
        "TipoMembresia": "No Forzoso",
        "Tarifa": "DOMICILIADO SIN PLAZO $599",
        "Total": 599,
        "FechaPago": "01-07-2026 08:05:00",
        "FechaRenovacion": "31-07-2026 23:59:59",
        "FechaFirmaContrato": None,
        "TipoPago": 2,
        "TipoTarjeta": None,
        "LugarPago": "Sucursal",
        "IDFolio": "12345678901234567890",
        "Pase": None,
        "Anfitrion": None,
        "TotalPagado": 599,
    }


def _xlsx_bytes(
    rows: list[dict[str, object]],
    *,
    headers: tuple[str, ...] = EXPECTED_COLUMNS,
) -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Socios"

    worksheet.append(list(headers))

    for row in rows:
        worksheet.append(
            [
                row.get(header)
                for header in headers
            ]
        )

    stream = BytesIO()
    workbook.save(stream)
    workbook.close()

    return stream.getvalue()


def test_parse_valid_row_and_resolve_branch():
    result = parse_ventas_nuevos_socios_detalle_xlsx(
        file_bytes=_xlsx_bytes([_base_row()]),
        branch_resolver=lambda _: 7,
    )

    assert result.row_count == 1
    assert result.row_count_valid == 1
    assert result.row_count_rejected == 0

    parsed_row = result.rows[0]

    assert parsed_row.id_socio == "123456"
    assert parsed_row.pin == "12345"
    assert parsed_row.sucursal_id == 7
    assert len(parsed_row.row_hash) == 64
    assert parsed_row.fecha_pago_at.tzinfo is not None


def test_blank_amounts_and_birth_sentinel_are_quality_flags():
    row = _base_row()

    row["FechaNacimiento"] = "31-12-9999"
    row["Total"] = ""
    row["TotalPagado"] = ""

    result = parse_ventas_nuevos_socios_detalle_xlsx(
        file_bytes=_xlsx_bytes([row]),
        branch_resolver=lambda _: 7,
    )

    parsed_row = result.rows[0]

    assert parsed_row.fecha_nacimiento is None
    assert parsed_row.total is None
    assert parsed_row.total_pagado is None

    assert (
        "BIRTH_DATE_SENTINEL"
        in parsed_row.quality_flags
    )

    assert (
        "TOTAL_MISSING"
        in parsed_row.quality_flags
    )

    assert (
        "TOTAL_PAGADO_MISSING"
        in parsed_row.quality_flags
    )


def test_duplicate_id_socio_rejects_second_row():
    first_row = _base_row()

    second_row = _base_row()
    second_row["IDFolio"] = "99999999999999999999"

    result = parse_ventas_nuevos_socios_detalle_xlsx(
        file_bytes=_xlsx_bytes(
            [
                first_row,
                second_row,
            ]
        ),
        branch_resolver=lambda _: 7,
    )

    assert result.row_count == 2
    assert result.row_count_valid == 1
    assert result.row_count_rejected == 1

    assert (
        result.rejected_rows[0].reason_code
        == "DUPLICATE_ID_SOCIO"
    )


def test_header_drift_raises_layout_error():
    invalid_headers = (
        *EXPECTED_COLUMNS[:-1],
        "Total Pago",
    )

    with pytest.raises(
        VentasNuevosSociosDetalleLayoutError
    ):
        parse_ventas_nuevos_socios_detalle_xlsx(
            file_bytes=_xlsx_bytes(
                [_base_row()],
                headers=invalid_headers,
            )
        )
