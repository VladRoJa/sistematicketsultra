from __future__ import annotations

import sqlite3
from datetime import date
from zipfile import ZipFile

import pytest
import xlsxwriter

from scripts.ops.consolidate_gasca_member_sales import _db_schema
from scripts.ops.export_member_streaks_presentation import (
    _best_run, _current_run, _month_number, _norm_id,
    generate, load_active,
)


def _active_xlsx(path):
    book = xlsxwriter.Workbook(str(path))
    ws = book.add_worksheet()
    ws.write("A1", "Reporte Socios Activos")
    ws.write_row("A2", [
        "#", "Pin", "Nombre", "Fecha Último Pago", "Fecha Vencimiento",
        "Sucursal", "Tarifa", "Importe Tarifa", "Fecha Ingreso",
        "Lada", "Teléfono", "Fecha Firma", "Aplica KPI", "Email", "ID Socio",
    ])
    samples = [
        ["1", "00001", "ALFA", "02/11/2026", "01/12/2026", "SUC A", "",
         "", "", "", "", "", "Si", "", "A"],
        ["2", "00002", "BETA", "15/10/2026", "15/11/2026", "SUC A", "",
         "", "", "", "", "", "No", "", "B"],
        ["3", "00003", "GAMMA", "25/10/2026", "25/11/2026", "SUC B", "",
         "", "", "", "", "", "Si", "", "C"],
        ["4", "00004", "DELTA", "25/10/2026", "25/11/2026", "SUC C", "",
         "", "", "", "", "", "Si", "", "D"],
    ]
    for i, sample in enumerate(samples, start=2):
        ws.write_row(i, 0, sample)
    book.close()


def _database(path):
    with sqlite3.connect(path) as conn:
        _db_schema(conn)
        events = [
            ("a1", "2026-09", "2026-09-15", "SUC A", "F-A1", "A", "00001",
             "CONTRATO", "DOMICILIADO", "ACTIVO", "599"),
            ("a2", "2026-10", "2026-10-15", "SUC A", "F-A2", "A", "00001",
             "CONTRATO", "DOMICILIADO", "ACTIVO", "599"),
            ("b1", "2026-10", "2026-10-15", "SUC A", "F-B1", "B", "00002",
             "MENSUAL SIN CONTRATO", "MENSUAL", "ACTIVO", "599"),
            ("d1", "2026-07", "2026-07-16", "SUC C", "F-D1", "D", "00004",
             "ANUALIDAD SIN CONTRATO", "ANUALIDAD", "ACTIVO", "5000"),
            ("e1", "2026-08", "2026-08-07", "SUC E", "F-E1", "E", "00005",
             "MENSUAL SIN CONTRATO", "MENSUAL", "ACTIVO", "599"),
            ("e2", "2026-09", "2026-09-07", "SUC E", "F-E2", "E", "00005",
             "MENSUAL SIN CONTRATO", "MENSUAL", "ACTIVO", "599"),
            ("e3", "2026-10", "2026-10-07", "SUC E", "F-E3", "E", "00005",
             "MENSUAL SIN CONTRATO", "MENSUAL", "ACTIVO", "599"),
            ("e4", "2026-10", "2026-10-08", "SUC E", "F-E4", "E", "00005",
             "MENSUAL SIN CONTRATO", "MENSUAL", "CANCELADO", "599"),
        ]
        conn.executemany("""
          INSERT INTO purchase_events (
            fingerprint, source_month, fecha, sucursal, folio,
            id_socio, pin, tipo, descripcion, estatus, total
          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, events)


def test_monthly_run_uses_recent_anchor_and_historical_best():
    months = {_month_number(x) for x in ("2026-02", "2026-03", "2026-07", "2026-08")}
    assert _best_run(months) == (2, _month_number("2026-07"), _month_number("2026-08"))
    assert _current_run(months, _month_number("2026-10")) == (0, None, None)
    assert _current_run(months, _month_number("2026-08")) == (
        2, _month_number("2026-07"), _month_number("2026-08"),
    )
    assert _norm_id("123.0") == "123"
    assert _norm_id("0001") == "0001"


def test_active_vs_historical_export_does_not_reclassify_kpi_no(tmp_path):
    source = tmp_path / "active.xlsx"
    _active_xlsx(source)
    db = tmp_path / "sales.sqlite"
    _database(db)
    out = tmp_path / "result.xlsx"
    result = generate(
        database=db, active_xlsx=source, output=out,
        as_of=date(2026, 11, 7), start_month="2026-07",
        end_month="2026-10",
    )
    assert result["activos_kpi_si"] == 3
    assert result["activos_sin_ventas"] == 1
    assert result["historicos_sin_activo"] == 1
    assert result["activos_excluidos_por_kpi"] == 1
    assert result["meses_sin_fuente"] == []
    assert result["niveles_activos"][1] == 1
    assert result["niveles_activos"][0] == 2
    assert result["niveles_historicos_provisionales"][1] == 1
    assert out.exists()
    assert not (tmp_path / "result.partial.xlsx").exists()
    with pytest.raises(FileExistsError, match="--replace"):
        generate(
            database=db, active_xlsx=source, output=out,
            as_of=date(2026, 11, 7), start_month="2026-07",
            end_month="2026-10",
        )
    with ZipFile(out) as archive:
        names = archive.namelist()
        assert "xl/worksheets/sheet1.xml" in names
        assert "xl/worksheets/sheet2.xml" in names
        assert "xl/worksheets/sheet3.xml" in names
        assert "xl/worksheets/sheet4.xml" in names
        xml_active = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")
        xml_expired = archive.read("xl/worksheets/sheet3.xml").decode("utf-8")
        assert "ALFA" in xml_active
        assert "GAMMA" in xml_active
        assert "DELTA" in xml_active
        assert "BETA" not in xml_expired
        assert "SIN_COMPRA_RECIENTE" in xml_active
        assert "NO DISPONIBLE" in xml_expired
        assert "E" in xml_expired
        assert "KPI" in xml_active


def test_report_duplicate_active_id_rejected(tmp_path):
    path = tmp_path / "dup.xlsx"
    _active_xlsx(path)
    assert len(load_active(path)[0]) == 4
    # Falta de base comprobada se reporta claramente sin crearla.
    with pytest.raises(FileNotFoundError):
        generate(
            database=tmp_path / "none.sqlite", active_xlsx=path,
            output=tmp_path / "out.xlsx", as_of=date(2026, 11, 7),
        )
