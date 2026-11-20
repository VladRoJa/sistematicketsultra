from openpyxl import Workbook
import pytest

from app.warehouse.services.ingresos_wellhub_parser import (
    IngresosWellhubParseError,
    parse_ingresos_wellhub_excel,
)


def _parse_report(tmp_path, *, sheet_name, headers, rows):
    path = tmp_path / "wellhub.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_name
    sheet["A1"] = "Consulta todos los check-ins del mes."
    sheet["A15"] = "Detalle"
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    workbook.save(path)

    return parse_ingresos_wellhub_excel(
        warehouse_upload_id=25393,
        file_path=str(path),
        original_filename=path.name,
        cutoff_date="2026-11-19",
    )


@pytest.mark.parametrize(
    ("location_id_header", "location_name_header"),
    [
        ("ID de ubicación", "Localización"),
        ("ID del centro", "Centro"),
        ("ID del centro", "Localización"),
    ],
)
def test_parse_checkins_detail_center_headers(
    tmp_path, location_id_header, location_name_header
):
    result = _parse_report(
        tmp_path,
        sheet_name="Información sobre check-ins",
        headers=[
            "Fecha", "Hora", location_id_header, location_name_header, "Visitante",
            "ID de Wellhub", "Producto", "Periodo de check-in", "Tipo de check-in",
            "Check-in extra", "Pago", "Moneda",
        ],
        rows=[
            ["2026-11-01", "09:59", "loc-1", "Sucursal prueba", "Visitante prueba",
             "1000000000000", "Acceso", "Estándar", "Visita", "No", 49, "MXN"],
            ["2026-11-19", "10:00", "loc-1", "Sucursal prueba", "Visitante prueba",
             "1000000000000", "Acceso", "Estándar", "Visita", "No", 60.04, "MXN"],
        ],
    )

    assert result["business_date"] == "2026-11-19"
    assert result["metadata"]["detected_layout"] == "checkins_detail"
    assert result["row_count_detected"] == 2
    assert result["row_count_valid"] == 1
    assert result["row_count_rejected"] == 0
    assert result["rows"] == [{
        "raw_branch_name": "Sucursal prueba",
        "visitor_name": "Visitante prueba",
        "wellhub_member_id": "1000000000000",
        "total_checkins_mtd": 2,
        "pago_total_mtd": pytest.approx(109.04),
    }]


def test_parse_visitors_summary(tmp_path):
    result = _parse_report(
        tmp_path,
        sheet_name="Datos de visitantes",
        headers=[
            "ID de ubicación", "Localización", "Visitante", "ID de Wellhub",
            "Total de check-ins", "Pago total",
        ],
        rows=[["loc-1", "Sucursal prueba", "Visitante prueba", "1000000000000", 2, 109.04]],
    )

    assert result["metadata"]["detected_layout"] == "summary_visitors"
    assert result["rows"][0]["total_checkins_mtd"] == 2
    assert result["rows"][0]["pago_total_mtd"] == pytest.approx(109.04)


def test_parse_checkins_detail_requires_payment_header(tmp_path):
    with pytest.raises(IngresosWellhubParseError, match="No se encontró un header compatible"):
        _parse_report(
            tmp_path,
            sheet_name="Información sobre check-ins",
            headers=["Fecha", "Hora", "ID del centro", "Centro", "Visitante", "ID de Wellhub"],
            rows=[["2026-11-01", "09:59", "loc-1", "Sucursal prueba", "Visitante prueba", "123"]],
        )
