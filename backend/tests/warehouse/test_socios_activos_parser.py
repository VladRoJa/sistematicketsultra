from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

import pandas as pd
import pytest

from app.warehouse.services.socios_activos_parser import (
    EXPECTED_SOCIOS_ACTIVOS_COLUMNS,
    SociosActivosLayoutError,
    parse_socios_activos_xlsx,
)


def _valid_row(
    *,
    row_number=1,
    aplica_kpi="Si",
):
    return [
        row_number,
        123,
        "PERSONA PRUEBA",
        datetime(2026, 8, 20, 10, 30, 0),
        datetime(2026, 9, 20, 23, 59, 59),
        "SUCURSAL TEST",
        "MENSUAL",
        599,
        datetime(2025, 1, 15, 8, 0, 0),
        686,
        "6861234567",
        datetime(2026, 1, 2, 12, 0, 0),
        aplica_kpi,
        "persona@example.com",
        987654,
    ]


def _build_xlsx_bytes(
    rows,
    *,
    headers=None,
):
    effective_headers = list(
        headers
        or EXPECTED_SOCIOS_ACTIVOS_COLUMNS
    )

    width = len(effective_headers)

    matrix = [
        [
            "Reporte Socios Activos",
            *([None] * (width - 1)),
        ],
        effective_headers,
        *rows,
    ]

    df = pd.DataFrame(matrix)

    buffer = BytesIO()

    df.to_excel(
        buffer,
        index=False,
        header=False,
    )

    return buffer.getvalue()


def test_parse_socios_activos_valid_row():
    result = parse_socios_activos_xlsx(
        file_bytes=_build_xlsx_bytes(
            [_valid_row()]
        )
    )

    assert result.report_type_key == "socios_activos"
    assert result.row_count_detected == 1
    assert result.row_count_valid == 1
    assert result.row_count_rejected == 0

    row = result.rows[0]

    assert row.row_index == 0
    assert row.source_row_number == 1

    assert row.id_socio == "987654"
    assert row.pin == "123"
    assert row.sucursal_raw == "SUCURSAL TEST"

    assert (
        row.fecha_vencimiento_date
        == date(2026, 9, 20)
    )

    assert (
        row.importe_tarifa
        == Decimal("599")
    )

    assert row.lada_raw == "686"
    assert row.telefono_raw == "6861234567"
    assert row.telefono_digits == "6861234567"

    assert row.aplica_kpi_raw == "Si"
    assert row.aplica_kpi is True

    assert row.email_raw == "persona@example.com"

    assert len(row.row_hash) == 64


def test_parse_socios_activos_preserves_non_kpi_active_member():
    result = parse_socios_activos_xlsx(
        file_bytes=_build_xlsx_bytes(
            [
                _valid_row(
                    aplica_kpi="No"
                ),
            ]
        )
    )

    assert result.row_count_valid == 1

    row = result.rows[0]

    assert row.aplica_kpi_raw == "No"
    assert row.aplica_kpi is False

    assert (
        result.data_quality_counts[
            "aplica_kpi_no"
        ]
        == 1
    )


def test_parse_socios_activos_rejects_unknown_aplica_kpi():
    invalid = _valid_row(
        row_number=2,
        aplica_kpi="Tal vez",
    )

    result = parse_socios_activos_xlsx(
        file_bytes=_build_xlsx_bytes(
            [
                _valid_row(),
                invalid,
            ]
        )
    )

    assert result.row_count_detected == 2
    assert result.row_count_valid == 1
    assert result.row_count_rejected == 1

    assert (
        result.rejected_rows[0].reason
        == "invalid_aplica_kpi"
    )


def test_parse_socios_activos_rejects_generated_footer():
    footer = [
        None,
        "Reporte generado: 25/08/2026",
        *([None] * 13),
    ]

    result = parse_socios_activos_xlsx(
        file_bytes=_build_xlsx_bytes(
            [
                _valid_row(),
                footer,
            ]
        )
    )

    assert result.row_count_detected == 2
    assert result.row_count_valid == 1
    assert result.row_count_rejected == 1

    assert (
        result.rejected_rows[0].reason
        == "empty_or_generated_business_row"
    )


def test_parse_socios_activos_requires_exact_contractual_layout():
    headers = list(
        EXPECTED_SOCIOS_ACTIVOS_COLUMNS
    )

    headers[-1] = "ID Socios"

    with pytest.raises(
        SociosActivosLayoutError
    ):
        parse_socios_activos_xlsx(
            file_bytes=_build_xlsx_bytes(
                [_valid_row()],
                headers=headers,
            )
        )
