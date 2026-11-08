from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path
from zipfile import ZipFile

import pytest
import xlsxwriter

from scripts.ops.consolidate_gasca_member_sales import _db_schema
from scripts.ops.prepare_gasca_sample_review import collect, write_review


def _active_report(path: Path) -> None:
    book = xlsxwriter.Workbook(str(path))
    ws = book.add_worksheet()
    ws.write("A1", "Reporte Socios Activos")
    ws.write_row("A2", [
        "#", "Pin", "Nombre", "Fecha Último Pago", "Fecha Vencimiento",
        "Sucursal", "Tarifa", "Importe Tarifa", "Fecha Ingreso",
        "Lada", "Teléfono", "Fecha Firma", "Aplica KPI", "Email", "ID Socio",
    ])
    for index, member, status, tariff in [
        (3, "A", "Si", "DOMICILIADO 12 MESES"),
        (4, "B", "No", "MENSUAL"),
        (5, "C", "Si", "ANUALIDAD"),
        (6, "D", "Si", "MENSUAL"),
    ]:
        ws.write_row(index-1, 0, [
            str(index), "00"+member, member, "25/09/2026", "01/12/2026",
            "SUC A", tariff, "", "", "", "", "", status, "", member,
        ])
    book.close()


def _database(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        _db_schema(conn)
        conn.executemany("""
          INSERT INTO purchase_events
          (fingerprint, source_month, fecha, sucursal, folio, id_socio,
           pin, tipo, descripcion, estatus, total)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            ("a1", "2026-10", "2026-10-05", "SUC A", "F1", "A",
             "00A", "CONTRATO", "DOMICILIADO", "ACTIVO", "499"),
            ("b1", "2026-10", "2026-10-06", "SUC A", "F2", "B",
             "00B", "MENSUAL SIN CONTRATO", "MENSUAL", "ACTIVO", "599"),
            ("c1", "2026-07", "2026-07-06", "SUC A", "F3", "C",
             "00C", "ANUALIDAD SIN CONTRATO", "ANUALIDAD", "ACTIVO", "2999"),
            ("c2", "2026-08", "2026-08-09", "SUC A", "F4", "C",
             "00C", "ANUALIDAD SIN CONTRATO", "REEMBOLSO", "CANCELADO", "2999"),
            ("e1", "2026-10", "2026-10-09", "SUC B", "F5", "E",
             "00E", "MENSUAL SIN CONTRATO", "MENSUAL", "ACTIVO", "599"),
        ])


def test_collect_sample_only_and_no_auto_paid_markers(tmp_path):
    roster, database = tmp_path / "activos.xlsx", tmp_path / "history.sqlite"
    _active_report(roster)
    _database(database)
    cases, events, meta = collect(
        database=database, active_xlsx=roster,
        as_of=date(2026, 11, 7), sales_cutoff="2026-10",
    )
    assert {c["id_socio"] for c in cases} == {"C", "D"}
    assert {m["id_socio"] for m in events} == {"C"}
    assert {m["folio"] for m in events} == {"F3", "F4"}
    assert any(m["estatus"] == "CANCELADO" for m in events)
    assert meta["casos"] == 2
    assert meta["movimientos_de_muestra"] == 2
    assert meta["casos_sin_movimientos"] == 1
    assert "00C" not in json.dumps(meta)
    assert "F3" not in json.dumps(meta)

    output = tmp_path / "revision.xlsx"
    write_review(output=output, sample=cases, movements=events, meta=meta)
    with pytest.raises(FileExistsError, match="--replace"):
        write_review(output=output, sample=cases, movements=events, meta=meta)
    assert output.exists()
    assert not (tmp_path / "revision.partial.xlsx").exists()
    with ZipFile(output) as zip_file:
        names = zip_file.namelist()
        assert "xl/worksheets/sheet1.xml" in names
        assert "xl/worksheets/sheet2.xml" in names
        combined = (zip_file.read("xl/worksheets/sheet1.xml").decode()
                    + zip_file.read("xl/worksheets/sheet2.xml").decode()
                    + zip_file.read("xl/sharedStrings.xml").decode())
        assert "PENDIENTE" in combined
        assert "COBRO_CONFIRMADO" in combined  # Opción, NO estado aplicado
        assert "F3" in combined and "F4" in combined
        shared_text = zip_file.read("xl/sharedStrings.xml").decode()
        assert "<t>F2</t>" not in shared_text
        assert "<t>F5</t>" not in shared_text
        assert "dataValidations" in combined


def test_cli_help_is_standalone(tmp_path):
    env = os.environ.copy()
    for key in ("SECRET_KEY", "JWT_SECRET_KEY", "SQLALCHEMY_DATABASE_URI"):
        env.pop(key, None)
    result = subprocess.run(
        [sys.executable, "-m", "scripts.ops.prepare_gasca_sample_review", "--help"],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True, text=True, env=env, timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert "--active-xlsx" in result.stdout
