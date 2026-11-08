from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile

import pytest

from scripts.ops import consolidate_gasca_member_sales as history


def _col(number: int) -> str:
    chars = ""
    while number:
        number, rest = divmod(number - 1, 26)
        chars = chr(65 + rest) + chars
    return chars


def _make_raw(path: Path, *, movement="02-01-20", id_socio="ID001",
              pin="0009", repeat=False):
    headers = list(history.COLUMNS)
    sales = [movement, "SUCURSAL A", "F001", "AB001", "MEM-1",
             "DOMICILIADO 12 MESES", "599", "ACTIVO", pin,
             "Contrato", id_socio]
    rows = [headers, sales] + ([sales] if repeat else [])
    xml = []
    for rowno, items in enumerate(rows, start=2):
        cells = [
            f'<c r="{_col(index)}{rowno}" t="inlineStr"><is>'
            f'<t>{escape(value)}</t></is></c>'
            for index, value in enumerate(items, start=1)
        ]
        xml.append(f'<row r="{rowno}">' + "".join(cells) + "</row>")
    data = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData>' + "".join(xml) + '</sheetData></worksheet>'
    )
    with ZipFile(path, "w") as zipped:
        zipped.writestr("xl/worksheets/sheet1.xml", data)


def _downloaded(root: Path, month: str, **kwargs) -> Path:
    path, manifest = history.paths(root, month)
    path.parent.mkdir(parents=True)
    _make_raw(path, **kwargs)
    manifest.write_text(json.dumps({
        "year_month": month, "sha256": history.sha256_file(path),
        "state": "RAW_ONLY_NON_CANONICAL"
    }), encoding="utf-8")
    return path


def test_month_range_includes_leap_year_and_validates():
    assert list(history.months(
        date(2020, 12, 1), date(2021, 2, 1)
    )) == ["2020-12", "2021-01", "2021-02"]
    with pytest.raises(ValueError):
        list(history.months(date(2021, 2, 1), date(2021, 1, 1)))


def test_build_stages_identified_sales_without_falsifying_paid_coverage(tmp_path):
    root = tmp_path / "private"
    raw = _downloaded(root, "2020-01", repeat=True)
    before = hashlib.sha256(raw.read_bytes()).hexdigest()
    result = history.consolidate(
        source_root=root,
        start=date(2020, 1, 1), end=date(2020, 3, 1),
        output_dir=root / "consolidated",
    )
    assert result["resumen"]["meses_ok"] == 1
    assert result["resumen"]["meses_sin_verificar"] == ["2020-02", "2020-03"]
    jan = result["meses"]["2020-01"]
    assert jan["metricas"]["membresia_identificada"] == 2
    assert jan["metricas"]["membresias_unicas"] == 1
    assert jan["metricas"]["renglones_identicos"] == 1
    assert before == hashlib.sha256(raw.read_bytes()).hexdigest()
    db_path = root / "consolidated" / "member_sales_202001_202003.sqlite"
    with sqlite3.connect(db_path) as db:
        record = db.execute(
            "SELECT id_socio, pin, descripcion, evidencia FROM purchase_events"
        ).fetchone()
        assert record == ("ID001", "0009", "DOMICILIADO 12 MESES",
                          "MOVIMIENTO_SIN_VIGENCIA")
        assert db.execute(
            "SELECT mes_movimiento, movimientos_membresia "
            "FROM member_month_sale_signals"
        ).fetchall() == [("2020-01", 1)]
    # El JSON agregado no filtra datos personales del ledger.
    quality = (root / "consolidated" / "member_sales_202001_202003_quality.json")
    assert "ID001" not in quality.read_text(encoding="utf-8")


def test_wrong_month_rolls_back_only_affected_source(tmp_path):
    root = tmp_path / "private"
    _downloaded(root, "2020-01")
    _downloaded(root, "2020-02", movement="10-01-20", id_socio="ID002")
    result = history.consolidate(
        source_root=root,
        start=date(2020, 1, 1), end=date(2020, 2, 1),
        output_dir=root / "consolidated",
    )
    assert result["meses"]["2020-02"]["estado"] == "ERROR_LECTURA_O_INTEGRIDAD"
    assert result["resumen"]["movimientos_candidatos_distintos"] == 1


def test_sha_mismatch_refused_and_partial_reported(tmp_path):
    root = tmp_path / "private"
    raw = _downloaded(root, "2020-01")
    raw.write_bytes(raw.read_bytes() + b"tampered")
    febraw, _ = history.paths(root, "2020-02")
    febraw.parent.mkdir(parents=True)
    febraw.with_name(febraw.stem + ".partial.xlsx").write_bytes(b"partial")
    result = history.consolidate(
        source_root=root,
        start=date(2020, 1, 1), end=date(2020, 2, 1),
        output_dir=root / "consolidated",
    )
    assert result["meses"]["2020-01"]["estado"] == "ERROR_LECTURA_O_INTEGRIDAD"
    assert result["meses"]["2020-02"]["estado"] == "DESCARGA_PARCIAL_NO_VALIDADA"
    assert result["resumen"]["movimientos_candidatos_distintos"] == 0


def test_existing_output_requires_replace(tmp_path):
    root = tmp_path / "raw"
    _downloaded(root, "2020-01")
    args = dict(source_root=root, start=date(2020, 1, 1),
                end=date(2020, 1, 1), output_dir=root / "consolidated")
    history.consolidate(**args)
    with pytest.raises(FileExistsError, match="replace"):
        history.consolidate(**args)
    assert history.consolidate(**args, replace=True)["resumen"]["meses_ok"] == 1
