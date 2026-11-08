from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.ops.audit_active_streak_gaps import audit, write_excel, _group
from scripts.ops.export_member_streaks_presentation import ActiveRow
import sqlite3
import xlsxwriter
from scripts.ops.consolidate_gasca_member_sales import _db_schema


def _active_xlsx(path):
    book = xlsxwriter.Workbook(str(path))
    ws = book.add_worksheet()
    ws.write("A1", "Reporte Socios Activos")
    ws.write_row("A2", [
        "#", "Pin", "Nombre", "Fecha Último Pago", "Fecha Vencimiento",
        "Sucursal", "Tarifa", "Importe Tarifa", "Fecha Ingreso",
        "Lada", "Teléfono", "Fecha Firma", "Aplica KPI", "Email", "ID Socio",
    ])
    for i, (mid, kpi, paid, tariff) in enumerate([
        ("A", "Si", "02/11/2026", "DOMICILIADO 12 MESES"),
        ("B", "No", "15/10/2026", "MENSUAL"),
        ("C", "Si", "25/10/2026", "MENSUAL"),
        ("D", "Si", "25/10/2026", "ANUALIDAD"),
    ], start=2):
        ws.write_row(i, 0, [
            str(i), "0000"+mid, mid, paid, "25/11/2026",
            "SUC A", tariff, "", "", "", "", "", kpi, "", mid,
        ])
    book.close()


def _database(path):
    with sqlite3.connect(path) as conn:
        _db_schema(conn)
        conn.executemany("""
            INSERT INTO purchase_events
            (fingerprint, source_month, fecha, sucursal, folio,
             id_socio, pin, tipo, descripcion, estatus, total)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            ("a1","2026-09","2026-09-04","SUC A","1","A","0000A",
             "CONTRATO","DOMICILIADO","ACTIVO","499"),
            ("a2","2026-10","2026-10-04","SUC A","2","A","0000A",
             "CONTRATO","DOMICILIADO","ACTIVO","499"),
            ("b1","2026-10","2026-10-05","SUC A","3","B","0000B",
             "MENSUAL SIN CONTRATO","MENSUAL","ACTIVO","599"),
            ("d1","2026-07","2026-07-07","SUC A","4","D","0000D",
             "ANUALIDAD SIN CONTRATO","ANUALIDAD","ACTIVO","3000"),
        ])


def test_audit_two_non_october_active_kpi_only(tmp_path):
    source, database = tmp_path / "active.xlsx", tmp_path / "history.sqlite"
    _active_xlsx(source)
    _database(database)
    summary, record_set = audit(
        database=database, active_xlsx=source,
        as_of=date(2026, 11, 7), sales_cutoff="2026-10",
    )
    rows = record_set[:-1]
    assert summary["activos_kpi_si"] == 3
    assert summary["activos_sin_compra_mes_corte"] == 2
    assert summary["activos_sin_ventas_historicas"] == 1
    assert summary["por_grupo_ultimo_pago_padron"]["SIN_HISTORIAL"] == 1
    assert summary["por_grupo_ultimo_pago_padron"]["PAGO_PADRON_MES_CORTE"] == 1
    assert {row["id_socio"] for row in rows} == {"C", "D"}
    assert next(r for r in rows if r["id_socio"] == "D")["tipo_ultima_compra"] == (
        "ANUALIDAD SIN CONTRATO"
    )
    # No se expone PII en resultados de consola.
    assert "00003" not in json.dumps(summary)
    assert "00004" not in json.dumps(summary)
    assert "ALFA" not in json.dumps(summary)

    output = tmp_path / "activos_revision.xlsx"
    write_excel(output=output, summary=summary, rows_and_sample=record_set)
    assert output.exists()
    assert not (tmp_path / "activos_revision.partial.xlsx").exists()
    with pytest.raises(FileExistsError, match="--replace"):
        write_excel(output=output, summary=summary, rows_and_sample=record_set)
    with ZipFile(output) as archive:
        assert all(
            f"xl/worksheets/sheet{i}.xml" in archive.namelist()
            for i in (1, 2, 3)
        )
        case_xml = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")
        shared = (
            archive.read("xl/sharedStrings.xml").decode("utf-8")
            if "xl/sharedStrings.xml" in archive.namelist() else ""
        )
        all_text = case_xml + shared
        assert "ANUALIDAD SIN CONTRATO" in all_text
        assert "SIN_HISTORIAL" in all_text
        assert "0000D" in all_text
        assert "0000B" not in all_text


def test_group_last_payment_never_certifies_coverage():
    sample = ActiveRow("1", "S", "", "", "SI",
                       "2026-11-02", "2026-12-02", "")
    assert _group(sample, cutoff="2026-10", has_sale=True) == (
        "PAGO_PADRON_MES_POSTERIOR"
    )
    assert _group(sample, cutoff="2026-10", has_sale=False) == "SIN_HISTORIAL"
    sample = ActiveRow("1", "S", "", "", "SI",
                       "2026-09-22", "2026-11-22", "")
    assert _group(sample, cutoff="2026-10", has_sale=True) == (
        "PAGO_PADRON_MES_ANTERIOR"
    )


def test_audit_invalid_cutoff_and_no_file(tmp_path):
    source, missing = tmp_path / "active.xlsx", tmp_path / "missing.sqlite"
    _active_xlsx(source)
    with pytest.raises(ValueError, match="posterior"):
        audit(database=missing, active_xlsx=source,
              sales_cutoff="2026-12", as_of=date(2026, 11, 7))
    with pytest.raises(FileNotFoundError):
        audit(database=missing, active_xlsx=source,
              sales_cutoff="2026-10", as_of=date(2026, 11, 7))
    assert not missing.exists()


def test_cli_help_needs_no_flask_secrets():
    env = os.environ.copy()
    for key in ("SECRET_KEY", "JWT_SECRET_KEY", "SQLALCHEMY_DATABASE_URI"):
        env.pop(key, None)
    result = subprocess.run(
        [sys.executable, "-m", "scripts.ops.audit_active_streak_gaps", "--help"],
        capture_output=True, text=True, env=env, timeout=20,
        cwd=Path(__file__).resolve().parents[2],
    )
    assert result.returncode == 0, result.stderr
    assert "--sales-cutoff" in result.stdout
