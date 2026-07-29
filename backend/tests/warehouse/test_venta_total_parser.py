from __future__ import annotations

from io import BytesIO

import pytest
from openpyxl import Workbook

from app.warehouse.services.venta_total_parser import (
    EXPECTED_VENTA_TOTAL_INTERNAL_COLUMNS,
    EXPECTED_VENTA_TOTAL_RAW_COLUMNS,
    VentaTotalLayoutError,
    parse_venta_total_xlsx,
)


BASE_ROW_VALUES = (
    1,
    "2026-07-28",
    "SUCURSAL SINTETICA",
    "FOLIO-SINTETICO-001",
    "CLAVE-SINTETICA",
    "PRODUCTO-SINTETICO",
    "DESCRIPCION SINTETICA",
    1,
    "100.00",
    "100.00",
    "16.00",
    "0.16",
    "116.00",
    "EFECTIVO",
    "PAGADO",
    None,
    "VENDEDOR SINTETICO",
    "10:30",
    "ORDEN-SINTETICA",
    None,
    "CAPTURISTA SINTETICO",
    "PIN-SINTETICO",
    "SOCIO-SINTETICO",
    "NO",
    "VENTA",
)

NEW_EXTRA_HEADERS = (
    "RFC",
    "Razon Social",
    "Fecha Facturacion",
    "Folio Interno Factura",
    "Telefono",
)

NEW_EXTRA_VALUES = (
    "RFC-SINTETICO",
    "RAZON SOCIAL SINTETICA",
    "2026-07-28",
    "FACTURA-SINTETICA",
    "TEL-SINTETICO-001",
)


def _xlsx_bytes(
    *,
    headers: tuple[str, ...] = EXPECTED_VENTA_TOTAL_RAW_COLUMNS,
    row_values: tuple[object, ...] = BASE_ROW_VALUES,
) -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Venta Total"
    worksheet.append(list(headers))
    worksheet.append(list(row_values))

    stream = BytesIO()
    workbook.save(stream)
    workbook.close()
    return stream.getvalue()


def test_parse_historical_file_without_telefono():
    result = parse_venta_total_xlsx(file_bytes=_xlsx_bytes())

    assert result.row_count == 1
    assert result.rows[0].telefono is None
    assert result.header_columns == EXPECTED_VENTA_TOTAL_INTERNAL_COLUMNS


def test_parse_new_file_with_extra_columns_after_tipo():
    result = parse_venta_total_xlsx(
        file_bytes=_xlsx_bytes(
            headers=(
                *EXPECTED_VENTA_TOTAL_RAW_COLUMNS,
                *NEW_EXTRA_HEADERS,
            ),
            row_values=(
                *BASE_ROW_VALUES,
                *NEW_EXTRA_VALUES,
            ),
        )
    )

    assert result.row_count == 1
    assert result.rows[0].telefono == "TEL-SINTETICO-001"
    assert result.header_columns[-5:] == NEW_EXTRA_HEADERS


@pytest.mark.parametrize("telefono", [None, "   "])
def test_parse_empty_telefono_as_none(telefono):
    result = parse_venta_total_xlsx(
        file_bytes=_xlsx_bytes(
            headers=(
                *EXPECTED_VENTA_TOTAL_RAW_COLUMNS,
                "Telefono",
            ),
            row_values=(
                *BASE_ROW_VALUES,
                telefono,
            ),
        )
    )

    assert result.rows[0].telefono is None


def test_parse_telefono_trims_surrounding_spaces():
    result = parse_venta_total_xlsx(
        file_bytes=_xlsx_bytes(
            headers=(
                *EXPECTED_VENTA_TOTAL_RAW_COLUMNS,
                "Telefono",
            ),
            row_values=(
                *BASE_ROW_VALUES,
                "  TEL-SINTETICO-ESPACIOS  ",
            ),
        )
    )

    assert result.rows[0].telefono == "TEL-SINTETICO-ESPACIOS"


def test_parse_accepts_accented_telefono_header():
    result = parse_venta_total_xlsx(
        file_bytes=_xlsx_bytes(
            headers=(
                *EXPECTED_VENTA_TOTAL_RAW_COLUMNS,
                "Teléfono",
            ),
            row_values=(
                *BASE_ROW_VALUES,
                "TEL-SINTETICO-ACENTO",
            ),
        )
    )

    assert result.rows[0].telefono == "TEL-SINTETICO-ACENTO"


def test_parse_still_requires_the_historical_25_column_prefix():
    invalid_headers = (
        *EXPECTED_VENTA_TOTAL_RAW_COLUMNS[:6],
        "Descripcion Alterada",
        *EXPECTED_VENTA_TOTAL_RAW_COLUMNS[7:],
        "Telefono",
    )

    with pytest.raises(VentaTotalLayoutError):
        parse_venta_total_xlsx(
            file_bytes=_xlsx_bytes(
                headers=invalid_headers,
                row_values=(
                    *BASE_ROW_VALUES,
                    "TEL-SINTETICO-INVALIDO",
                ),
            )
        )
