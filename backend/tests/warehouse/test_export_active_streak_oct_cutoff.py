from __future__ import annotations

import sqlite3
from datetime import date
from zipfile import ZipFile

import pytest
import xlsxwriter

from scripts.ops.consolidate_gasca_member_sales import _db_schema
from scripts.ops.export_active_streak_oct_cutoff import (
    CUTOFF, active_streak, add_months, generate, inferred_months,
)


def test_cutoff_ends_in_october_without_counting_prepaid_future():
    # Pago de mayo + vencimiento diciembre = seis MESES ALCANZADOS en octubre.
    last = active_streak(
        last_paid="2026-05-11", expires="2026-12-11", historic=[],
    )
    assert last["racha"] == 6
    assert last["desde"] == "2026-05-11"
    assert all(last["months"][m] == "V" for m in (
        "2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10",
    ))
    assert "2026-11" not in last["months"]
    assert last["estimados"] == 0

    joined = active_streak(
        last_paid="2026-05-11", expires="2026-12-11",
        historic=[(date(2026, 3, 11), date(2026, 5, 11), "VENTA_INFERIDA")],
    )
    assert joined["racha"] == 8
    assert joined["desde"] == "2026-03-11"
    assert joined["months"]["2026-03"] == "E"
    assert joined["months"]["2026-04"] == "E"
    assert joined["months"]["2026-05"] == "V"
    assert joined["months"]["2026-10"] == "V"
    assert joined["evidencia"] == "PADRON_Y_VENTAS_ESTIMADAS"


def test_real_gap_breaks_streak_and_november_purchase_is_not_counted():
    split = active_streak(
        last_paid="2026-09-01", expires="2026-11-01",
        historic=[(date(2026, 1, 1), date(2026, 6, 1), "VENTA_INFERIDA")],
    )
    assert split["racha"] == 2
    assert split["desde"] == "2026-09-01"
    future = active_streak(
        last_paid="2026-11-01", expires="2026-12-01", historic=[],
    )
    assert future["racha"] is None
    assert future["evidencia"] == "SIN_COBERTURA_OBSERVABLE_AL_CORTE"


def test_modalities_prepay_but_contract_remains_monthly():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert inferred_months("CONTRATO", "DOMICILIADO 12 MESES") == 1
    assert inferred_months("SEMESTRAL SIN CONTRATO", "SEMESTRAL MAYO 7 MESES $2999") == 7
    assert inferred_months("ANUALIDAD SIN CONTRATO", "ANUALIDAD 13 MESES") == 13
    assert inferred_months("ANUALIDAD SIN CONTRATO", "ANUALIDAD + 3 MESES REGALO") == 12
    assert inferred_months("SEMANAL SIN CONTRATO", "SEMANAL") is None


def _roster(path):
    book = xlsxwriter.Workbook(str(path))
    ws = book.add_worksheet()
    ws.write("A1", "Reporte Socios Activos")
    ws.write_row("A2", [
        "#", "Pin", "Nombre", "Fecha Último Pago",
        "Fecha Vencimiento", "Sucursal", "Tarifa", "Importe Tarifa",
        "Fecha Ingreso", "Lada", "Teléfono", "Fecha Firma",
        "Aplica KPI", "Email", "ID Socio",
    ])
    rows = [
        ("A", "SI", "11/05/2026", "11/12/2026", "SEMESTRAL MAYO 7 MESES"),
        ("B", "NO", "11/05/2026", "11/12/2026", "SEMESTRAL MAYO 7 MESES"),
        ("C", "SI", "01/11/2026", "01/12/2026", "MENSUAL"),
    ]
    for i, (member, kpi, paid, expires, tarifa) in enumerate(rows, start=2):
        ws.write_row(i, 0, [
            str(i), "00"+member, "SOCIO PRUEBA "+member, paid, expires,
            "TEC MXL", tarifa, "", "", "", "", "", kpi, "", member,
        ])
    book.close()


def _sqlite(path):
    with sqlite3.connect(path) as conn:
        _db_schema(conn)
        conn.executemany("""
          INSERT INTO purchase_events (
            fingerprint, source_month, fecha, sucursal, folio,
            id_socio, pin, tipo, descripcion, estatus, total
          ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, [
            ("1", "2026-03", "2026-03-11", "TEC MXL", "f1", "A", "00A",
             "BIMESTRAL SIN CONTRATO", "BIMESTRAL", "ACTIVO", "999"),
            ("2", "2026-10", "2026-10-10", "TEC MXL", "f2", "B", "00B",
             "MENSUAL SIN CONTRATO", "MENSUAL", "ACTIVO", "599"),
            ("3", "2026-10", "2026-10-10", "TEC MXL", "f3", "C", "00C",
             "MENSUAL SIN CONTRATO", "MENSUAL", "CANCELADO", "599"),
        ])


def test_single_sheet_eligible_only_october_cutoff(tmp_path):
    roster, db, output = (
        tmp_path/"activos.xlsx", tmp_path/"sales.sqlite", tmp_path/"result.xlsx"
    )
    _roster(roster)
    _sqlite(db)
    result = generate(database=db, active_xlsx=roster, output=output)
    assert result["activos_kpi_si"] == 2
    assert result["activos_procesados"] == 2
    assert result["evidencia"]["PADRON_Y_VENTAS_ESTIMADAS"] == 1
    assert result["evidencia"]["SIN_COBERTURA_OBSERVABLE_AL_CORTE"] == 1
    assert output.exists()
    with ZipFile(output) as z:
        wb_xml = z.read("xl/workbook.xml").decode()
        assert wb_xml.count("<sheet ") == 1
        sheet_xml = z.read("xl/worksheets/sheet1.xml").decode()
        assert "SOCIO PRUEBA A" in sheet_xml
        assert "SOCIO PRUEBA B" not in sheet_xml
        assert "SOCIO PRUEBA C" in sheet_xml
        assert "2026-11" not in sheet_xml  # No meses futuros
    with pytest.raises(FileExistsError):
        generate(database=db, active_xlsx=roster, output=output)
