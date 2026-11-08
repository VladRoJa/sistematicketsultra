from __future__ import annotations

import json
import sqlite3
from datetime import date
from zipfile import ZipFile

import pytest
import xlsxwriter

from scripts.ops.consolidate_gasca_member_sales import _db_schema
from scripts.ops.export_expired_streak_oct_cutoff import (
    best_historical_streak, generate, iter_expired_roster,
)
from scripts.ops.export_active_streak_oct_cutoff import add_months


def _roster(path):
    wb = xlsxwriter.Workbook(str(path))
    ws = wb.add_worksheet()
    ws.write("A1", "Socios Activos")
    ws.write_row("A2", [
        "#", "Pin", "Nombre", "Fecha Último Pago",
        "Fecha Vencimiento", "Sucursal", "Tarifa", "Importe Tarifa",
        "Fecha Ingreso", "Lada", "Teléfono", "Fecha Firma",
        "Aplica KPI", "Email", "ID Socio",
    ])
    ws.write_row("A3", [
        "1", "00A", "ACTIVO SI", "01/10/2026", "01/11/2026",
        "TEC MXL", "MENSUAL", "", "", "", "", "", "Si", "", "A",
    ])
    ws.write_row("A4", [
        "2", "00B", "ACTIVO NO", "01/10/2026", "01/11/2026",
        "TEC MXL", "MENSUAL", "", "", "", "", "", "No", "", "B",
    ])
    wb.close()


def _vencidos(path):
    wb = xlsxwriter.Workbook(str(path))
    ws = wb.add_worksheet()
    ws.write("A1", "Socios Vencidos")
    ws.write_row("A2", [
        "#", "Pin", "Nombre", "Genero", "Edad",
        "Fecha Vencimiento", "Fecha Último Pago", "Tarifa", "Correo",
        "Teléfono", "Sucursal", "Adeudo",
    ])
    ws.write_row("A3", [
        "1", "00C", "PERSONA HISTORICA C", "", "",
        "20/12/2026", "20/12/2025", "ANUALIDAD 13 MESES",
        "", "", "TEC MXL", "",
    ])
    # El PIN compartido por D y E es ambiguo y no autoriza inventar nombre.
    ws.write_row("A4", [
        "2", "00D", "NOMBRE NO CONFIABLE", "", "",
        "05/04/2026", "05/03/2026", "MENSUAL", "", "", "TEC MXL", "",
    ])
    ws.write_row("A5", [
        "3", "00A", "ACTIVO VISTO EN MUESTRA", "", "",
        "01/10/2026", "01/09/2026", "MENSUAL", "", "", "TEC MXL", "",
    ])
    wb.close()


def _database(path):
    with sqlite3.connect(path) as c:
        _db_schema(c)
        c.executemany("""
            INSERT INTO purchase_events
            (fingerprint, source_month, fecha, sucursal, folio, id_socio,
             pin, tipo, descripcion, estatus, total)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            ("a1","2026-10","2026-10-01","TEC MXL","F1","A","00A",
             "MENSUAL SIN CONTRATO","MENSUAL","ACTIVO","599"),
            ("b1","2026-10","2026-10-01","TEC MXL","F2","B","00B",
             "MENSUAL SIN CONTRATO","MENSUAL","ACTIVO","599"),
            ("c1","2025-12","2025-12-20","TEC MXL","F3","C","00C",
             "ANUALIDAD SIN CONTRATO","ANUALIDAD 13 MESES","ACTIVO","3999"),
            ("d1","2026-03","2026-03-05","TEC MXL","F4","D","00D",
             "MENSUAL SIN CONTRATO","MENSUAL","ACTIVO","599"),
            ("d2","2026-04","2026-04-05","TEC MXL","F5","D","00D",
             "MENSUAL SIN CONTRATO","MENSUAL","ACTIVO","599"),
            ("d3","2026-09","2026-09-05","TEC MXL","F6","D","00D",
             "MENSUAL SIN CONTRATO","MENSUAL","ACTIVO","599"),
            ("e1","2026-08","2026-08-05","TEC MXL","F7","E","00D",
             "MENSUAL SIN CONTRATO","MENSUAL","CANCELADO","599"),
            ("f1","2026-01","2026-01-05","TEC MXL","F8","F","00F",
             "SEMANAL SIN CONTRATO","SEMANAL","ACTIVO","159"),
        ])



def _raw_venta_total(root):
    # El RAW real contiene Socio y IDSocio en la misma fila.
    rows = [
        ("2025-12", "C", "PERSONA RAW C", "ANUALIDAD SIN CONTRATO"),
        ("2026-03", "D", "PERSONA RAW D", "MENSUAL SIN CONTRATO"),
        ("2026-08", "E", "PERSONA RAW E", "MENSUAL SIN CONTRATO"),
        ("2026-09", "D", "PERSONA RAW D ACTUALIZADA", "MENSUAL SIN CONTRATO"),
        ("2026-10", "A", "ACTIVO DESDE RAW", "MENSUAL SIN CONTRATO"),
    ]
    for month, member, name, kind in rows:
        folder = root / month
        folder.mkdir(parents=True, exist_ok=True)
        filename = f"venta_total_{month.replace('-', '_')}_gasca_original.xlsx"
        wb = xlsxwriter.Workbook(str(folder / filename))
        ws = wb.add_worksheet()
        ws.write("A1", "Reporte Venta Total")
        ws.write_row("A2", ["IDSocio", "Socio", "Tipo"])
        ws.write_row("A3", [member, name, kind])
        wb.close()


def test_best_historical_streak_not_anchored_to_october():
    blocks = [
        (date(2024, 1, 1), add_months(date(2024, 1, 1), 3), "VENTA_INFERIDA"),
        (date(2026, 9, 1), add_months(date(2026, 9, 1), 1), "VENTA_INFERIDA"),
    ]
    best = best_historical_streak(blocks)
    assert best["mejor"] == 3
    assert best["inicio"] == "2024-01-01"
    assert best["fin"] == "2024-03-31"
    assert best["meses"] == {"2024-01", "2024-02", "2024-03"}
    assert "2026-09" not in best["meses"]


def test_export_all_historical_ids_unique_names_only(tmp_path):
    active, expired, db, dest = (
        tmp_path/"active.xlsx", tmp_path/"vencidos.xlsx",
        tmp_path/"ventas.sqlite", tmp_path/"vencidos_resultado.xlsx",
    )
    _roster(active)
    _vencidos(expired)
    _database(db)
    root = tmp_path / "venta_total_raw"
    _raw_venta_total(root)
    assert sum(1 for _ in iter_expired_roster(expired)) == 3
    result = generate(
        database=db, active_xlsx=active, expired_xlsx=expired, output=dest,
        raw_root=root,
    )
    assert result["historicos_sin_activo"] == 4
    assert result["activos_excluidos"] == 2  # Excluye KPI=Si y KPI=No
    assert result["con_mejor_racha"] == 2  # C y D
    assert result["sin_racha_inferible"] == 2  # E cancelado y F semanal
    assert result["nombres_recuperados"] == 3
    assert result["nombres_venta_total_raw"]["ids_con_nombre_raw"] == 3
    assert result["nombres_no_disponibles"] == 1
    assert result["muestra_vencidos"]["sin_id_unico"] == 1
    assert result["muestra_vencidos"]["coincidentes_con_activos_excluidos"] == 1
    assert result["movimientos_inferidos"] == 4
    with ZipFile(dest) as archive:
        workbook = archive.read("xl/workbook.xml").decode()
        sheet = archive.read("xl/worksheets/sheet1.xml").decode()
        assert workbook.count("<sheet ") == 1
        assert "PERSONA RAW C" in sheet
        assert "PERSONA RAW D ACTUALIZADA" in sheet
        assert "PERSONA RAW E" in sheet
        assert "PERSONA HISTORICA C" not in sheet
        assert "NOMBRE NO CONFIABLE" not in sheet
        assert "ACTIVO VISTO EN MUESTRA" not in sheet
        assert "ACTIVO SI" not in sheet
        assert "ACTIVO NO" not in sheet
        assert "SOLO_VENTAS_ESTIMADAS" in sheet
        assert "<t>2026-11</t>" not in sheet
        # Anualidad de diciembre 2025 a octubre 2026 = 11 meses
        from xml.etree import ElementTree as ET
        ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        xml_root = ET.fromstring(sheet)
        rows = xml_root.findall(".//x:sheetData/x:row", ns)
        # Orden por ID: C, D, E, F, primera fila de datos fila 6
        assert xml_xml_root.find(".//x:c[@r='I6']/x:v", ns).text == "11"
        assert xml_root.find(".//x:c[@r='I7']/x:v", ns).text == "3"
        assert xml_root.find(".//x:c[@r='I8']", ns) is None
        assert xml_root.find(".//x:c[@r='I9']", ns) is None
    with pytest.raises(FileExistsError):
        generate(
            database=db, active_xlsx=active, expired_xlsx=expired, output=dest,
            raw_root=root,
        )


def test_optional_expired_report_and_missing_source(tmp_path):
    active, db, dest = (
        tmp_path/"active.xlsx", tmp_path/"ventas.sqlite",
        tmp_path/"historicos.xlsx",
    )
    _roster(active)
    _database(db)
    root = tmp_path / "venta_total_raw"
    _raw_venta_total(root)
    result = generate(database=db, active_xlsx=active, output=dest, raw_root=root)
    assert result["historicos_sin_activo"] == 4
    assert result["nombres_recuperados"] == 3
    with pytest.raises(FileNotFoundError):
        generate(
            database=tmp_path/"missing.sqlite", active_xlsx=active,
            output=tmp_path/"other.xlsx",
        )
