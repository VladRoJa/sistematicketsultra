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
from tests.warehouse.test_export_member_streaks_presentation import (
    _active_xlsx, _database,
)


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
        cases_xml = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")
        assert "ANUALIDAD SIN CONTRATO" in cases_xml
        assert "SIN_HISTORIAL" in cases_xml
        assert "00004" in cases_xml
        assert "00002" not in cases_xml


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
