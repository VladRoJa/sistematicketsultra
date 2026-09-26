from datetime import date

import pandas as pd

from app.sports_analysis.attendance_parser import (
    parse_attendance_excel,
)


COLUMNS = [
    "",
    "Pin",
    "Entrada",
    "Salida",
    "Nombre",
    "Apellido",
    "Edad",
    "Ciudad",
    "Sucursal",
    "CP",
    "Alta",
    "Tipo Asistencia",
    "Tiene Apertura",
]


def _write_report(path, rows):
    title = [
        "Reporte De Estadisticas De Asistencias",
        *([None] * (len(COLUMNS) - 1)),
    ]
    footer = [
        "Reporte generado: 19-06-2026 05:25 p. m.",
        *([None] * (len(COLUMNS) - 1)),
    ]
    pd.DataFrame(
        [title, COLUMNS, *rows, footer]
    ).to_excel(
        path,
        index=False,
        header=False,
    )


def _row(
    *,
    pin="00123",
    entry="18-06-2026 06:00:00",
    exit_value="18-06-2026 07:30:00",
    age="29",
):
    return [
        "",
        pin,
        entry,
        exit_value,
        "Ana",
        "Prueba",
        age,
        "MEXICALI",
        "SEND MXL",
        "21000",
        "01-01-2025",
        "SOCIO",
        "No",
    ]


def test_parser_preserves_pin_and_visit_state(tmp_path):
    report = tmp_path / "attendance.xlsx"
    _write_report(
        report,
        [
            _row(),
            _row(
                pin="00999",
                entry="18-06-2026 08:00:00",
                exit_value="SIN SALIDA",
                age="-7973",
            ),
        ],
    )

    result = parse_attendance_excel(
        report,
        business_date=date(2026, 6, 18),
    )

    assert result.source_rows == 2
    assert len(result.rejections) == 0

    closed, opened = result.visits

    assert closed.member_pin == "00123"
    assert closed.visit_status == "CLOSED"
    assert closed.duration_seconds == 90 * 60
    assert closed.age == 29
    assert closed.age_is_valid is True

    assert opened.member_pin == "00999"
    assert opened.visit_status == "OPEN"
    assert opened.exited_at_utc is None
    assert opened.age is None
    assert opened.age_is_valid is False


def test_fingerprint_is_stable_when_exit_is_completed(tmp_path):
    open_report = tmp_path / "open.xlsx"
    closed_report = tmp_path / "closed.xlsx"

    _write_report(
        open_report,
        [_row(exit_value="SIN SALIDA")],
    )
    _write_report(
        closed_report,
        [
            _row(
                exit_value="18-06-2026 07:30:00"
            )
        ],
    )

    opened = parse_attendance_excel(
        open_report,
        business_date=date(2026, 6, 18),
    ).visits[0]
    closed = parse_attendance_excel(
        closed_report,
        business_date=date(2026, 6, 18),
    ).visits[0]

    assert opened.visit_status == "OPEN"
    assert closed.visit_status == "CLOSED"
    assert (
        opened.source_fingerprint
        == closed.source_fingerprint
    )


def test_business_date_mismatch_is_rejected(tmp_path):
    report = tmp_path / "mismatch.xlsx"
    _write_report(
        report,
        [
            _row(
                entry="17-06-2026 23:00:00",
                exit_value="18-06-2026 00:10:00",
            )
        ],
    )

    result = parse_attendance_excel(
        report,
        business_date=date(2026, 6, 18),
    )

    assert result.source_rows == 1
    assert len(result.visits) == 0
    assert len(result.rejections) == 1
    assert (
        result.rejections[0].reason_code
        == "BUSINESS_DATE_MISMATCH"
    )
