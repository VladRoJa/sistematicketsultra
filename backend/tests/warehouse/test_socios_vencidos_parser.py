from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
import pytest

from app.warehouse.services.socios_vencidos_parser import (
    EDAD_STATUS_INVALID_OUT_OF_RANGE,
    EDAD_STATUS_MISSING,
    EDAD_STATUS_VALID,
    EXPECTED_SOCIOS_VENCIDOS_COLUMNS,
    SociosVencidosLayoutError,
    parse_socios_vencidos_xlsx,
)


def _base_row(**overrides: object) -> list[object]:
    values: dict[str, object] = {
        "source_row_number": 1,
        "pin": 12345,
        "nombre": "PERSONA FICTICIA",
        "genero": "F",
        "edad": 30,
        "fecha_vencimiento": "23/08/2026 14:25:51",
        "fecha_ultimo_pago": "22/08/2026 10:00:00",
        "tarifa": "TARIFA FICTICIA",
        "correo": "persona@example.invalid",
        "telefono": 6641234567,
        "sucursal": "SUCURSAL FICTICIA",
        "adeudo": "999.00",
    }
    values.update(overrides)
    return list(values.values())


def _xlsx_bytes(
    *,
    rows: list[list[object]] | None = None,
    headers: list[object] | None = None,
) -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Socios vencidos"
    worksheet.append(["REPORTE FICTICIO"])
    worksheet.append(
        headers
        or [None, *EXPECTED_SOCIOS_VENCIDOS_COLUMNS[1:]]
    )
    for row in rows or [_base_row()]:
        worksheet.append(row)

    stream = BytesIO()
    workbook.save(stream)
    workbook.close()
    return stream.getvalue()


def test_detects_second_row_header_and_blank_source_column():
    result = parse_socios_vencidos_xlsx(
        file_bytes=_xlsx_bytes(
            rows=[
                _base_row(),
                ["Reporte generado: 24/08/2026"],
            ]
        )
    )

    assert result.header_columns == EXPECTED_SOCIOS_VENCIDOS_COLUMNS
    assert result.row_count_detected == 2
    assert result.row_count_valid == 1
    assert result.row_count_rejected == 1
    assert result.rows[0].source_row_number == 1
    assert result.rejected_rows[0].reason == (
        "empty_or_generated_business_row"
    )


@pytest.mark.parametrize(
    ("raw_pin", "expected"),
    [
        (12345, "12345"),
        (12345.0, "12345"),
        ("1.2345E+4", "12345"),
        ("0012345", "0012345"),
    ],
)
def test_pin_is_preserved_as_text_without_excel_numeric_artifacts(
    raw_pin: object,
    expected: str,
):
    result = parse_socios_vencidos_xlsx(
        file_bytes=_xlsx_bytes(
            rows=[_base_row(pin=raw_pin)]
        )
    )

    assert result.rows[0].pin == expected


@pytest.mark.parametrize(
    ("raw_phone", "expected"),
    [
        (6641234567, "6641234567"),
        (6641234567.0, "6641234567"),
        ("6.641234567E+9", "6641234567"),
    ],
)
def test_phone_keeps_raw_text_and_digits_without_dot_zero(
    raw_phone: object,
    expected: str,
):
    result = parse_socios_vencidos_xlsx(
        file_bytes=_xlsx_bytes(
            rows=[_base_row(telefono=raw_phone)]
        )
    )

    assert result.rows[0].telefono_raw == expected
    assert result.rows[0].telefono_digits == expected


@pytest.mark.parametrize(
    "raw_expiration",
    [
        datetime(2026, 8, 23, 14, 25, 51),
        date(2026, 8, 23),
        "23/08/2026 14:25:51",
    ],
)
def test_dates_accept_excel_and_string_types_and_derive_civil_date(
    raw_expiration: object,
):
    result = parse_socios_vencidos_xlsx(
        file_bytes=_xlsx_bytes(
            rows=[
                _base_row(
                    fecha_vencimiento=raw_expiration
                )
            ]
        )
    )

    assert result.rows[0].fecha_vencimiento_date == date(
        2026,
        8,
        23,
    )
    assert result.rows[0].fecha_vencimiento_local.tzinfo is None


def test_last_payment_is_nullable():
    result = parse_socios_vencidos_xlsx(
        file_bytes=_xlsx_bytes(
            rows=[_base_row(fecha_ultimo_pago=None)]
        )
    )

    assert result.rows[0].fecha_ultimo_pago_local is None


def test_debt_is_decimal():
    result = parse_socios_vencidos_xlsx(
        file_bytes=_xlsx_bytes(
            rows=[_base_row(adeudo="$1,234.50")]
        )
    )

    assert result.rows[0].adeudo == Decimal("1234.50")


def test_valid_age_preserves_raw_and_normalized_value():
    result = parse_socios_vencidos_xlsx(
        file_bytes=_xlsx_bytes(
            rows=[_base_row(edad=30)]
        )
    )

    row = result.rows[0]
    assert row.edad_raw == 30
    assert row.edad == 30
    assert row.edad_status == EDAD_STATUS_VALID
    assert result.data_quality_counts == {
        "invalid_edad": 0,
        "missing_edad": 0,
    }


def test_out_of_range_age_is_valid_row_with_quality_warning():
    result = parse_socios_vencidos_xlsx(
        file_bytes=_xlsx_bytes(
            rows=[_base_row(edad=-7974)]
        )
    )

    row = result.rows[0]
    assert row.edad_raw == -7974
    assert row.edad is None
    assert row.edad_status == EDAD_STATUS_INVALID_OUT_OF_RANGE
    assert result.row_count_valid == 1
    assert result.row_count_rejected == 0
    assert result.data_quality_counts == {
        "invalid_edad": 1,
        "missing_edad": 0,
    }


def test_missing_age_is_valid_row_with_missing_status():
    result = parse_socios_vencidos_xlsx(
        file_bytes=_xlsx_bytes(
            rows=[_base_row(edad=None)]
        )
    )

    row = result.rows[0]
    assert row.edad_raw is None
    assert row.edad is None
    assert row.edad_status == EDAD_STATUS_MISSING
    assert result.row_count_valid == 1
    assert result.row_count_rejected == 0
    assert result.data_quality_counts == {
        "invalid_edad": 0,
        "missing_edad": 1,
    }


def test_missing_required_column_rejects_layout():
    headers = [None, *EXPECTED_SOCIOS_VENCIDOS_COLUMNS[1:-1]]
    row = _base_row()[:-1]

    with pytest.raises(SociosVencidosLayoutError):
        parse_socios_vencidos_xlsx(
            file_bytes=_xlsx_bytes(
                headers=headers,
                rows=[row],
            )
        )


def test_invalid_required_row_is_counted_without_exposing_values():
    result = parse_socios_vencidos_xlsx(
        file_bytes=_xlsx_bytes(
            rows=[
                _base_row(),
                _base_row(
                    source_row_number=2,
                    sucursal=None,
                ),
            ]
        )
    )

    assert result.row_count_detected == 2
    assert result.row_count_valid == 1
    assert result.row_count_rejected == 1
    assert result.rejected_rows[0].source_row_number == 2
    assert result.rejected_rows[0].reason == "missing_required_sucursal"


def test_row_hash_depends_on_content_not_source_position():
    result = parse_socios_vencidos_xlsx(
        file_bytes=_xlsx_bytes(
            rows=[
                _base_row(source_row_number=1),
                _base_row(source_row_number=99),
            ]
        )
    )

    assert result.rows[0].row_index != result.rows[1].row_index
    assert result.rows[0].source_row_number != (
        result.rows[1].source_row_number
    )
    assert result.rows[0].row_hash == result.rows[1].row_hash


def test_parser_accepts_file_path(tmp_path):
    xlsx_path = tmp_path / "socios-vencidos-ficticio.xlsx"
    xlsx_path.write_bytes(_xlsx_bytes())

    result = parse_socios_vencidos_xlsx(
        file_path=str(xlsx_path)
    )

    assert result.row_count_valid == 1
