from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile

import pytest
from flask import Flask

from app.warehouse.backfill import redownload_venta_total_history as history


def _xlsx(path: Path, *, movement_date="01-12-24", id_socio="1001", pin="55"):
    headers = ["#", "Fecha", "Sucursal", "Folio", "Clave", "Clave Producto",
               "Descripcion", "Cant.", "Prec. Unit.", "Subtotal", "IVA", "IVA",
               "Total", "Forma De Pago", "Estatus", "Motivo", "Realizo Venta",
               "Hora", "IDOrden", "Encuesta", "Capturista", "PIN", "Socio",
               "Nuevo", "Tipo", "RFC", "Razon Social", "Fecha Facturacion",
               "Folio Interno Factura", "Telefono", "Api", "IDSocio"]
    values = ["1", movement_date, "SUCURSAL QA", "24190301920200099", "",
              "", "MENSUALIDAD", "1", "599", "599", "0", "0",
              "599", "EFECTIVO", "ACTIVO", "", "", "", "", "", "",
              pin, "", "", "Contrato", "", "", "", "", "", "", id_socio]

    def row_xml(i, entries):
        cells = []
        for index, value in enumerate(entries):
            if value is None:
                continue
            col = history._excel_column(index + 1) if hasattr(
                history, "_excel_column"
            ) else (
                chr(65 + index) if index < 26 else "A" + chr(65 + index - 26)
            )
            cells.append(
                f'<c r="{col}{i}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
            )
        return f'<row r="{i}">' + "".join(cells) + "</row>"

    rows = [
        row_xml(1, ["Reporte Venta Total"]),
        row_xml(2, headers),
        row_xml(3, values),
        row_xml(4, [*values[:3], "24190301920200100", *values[4:]]),
    ]
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData>' + "".join(rows) + '</sheetData></worksheet>'
    )
    with ZipFile(path, "w") as zip_file:
        zip_file.writestr("xl/worksheets/sheet1.xml", xml.encode())


def test_month_boundaries_and_invalid_selection():
    assert list(history.iter_month_ends(
        date(2023, 12, 1), date(2024, 2, 1)
    )) == [date(2023, 12, 31), date(2024, 1, 31), date(2024, 2, 29)]
    with pytest.raises(ValueError):
        list(history.iter_month_ends(date(2024, 2, 1), date(2024, 1, 1)))
    with pytest.raises(ValueError):
        history.parse_month("2024-13")


def test_identity_and_membership_profile_on_raw_file(tmp_path):
    path = tmp_path / "Reporte Venta Total.xlsx"
    _xlsx(path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    result = history.profile_download(path, expected_month=date(2024, 12, 31))
    assert result["rows"] == 2
    assert result["rows_with_pin"] == 2
    assert result["rows_with_idsocio"] == 2
    assert result["candidate_membership_rows"] == 2
    assert result["identity_available"] is True
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_missing_identity_not_silently_marked_good(tmp_path):
    path = tmp_path / "empty_ids.xlsx"
    _xlsx(path, pin="", id_socio="")
    result = history.profile_download(path, expected_month=date(2024, 12, 31))
    assert result["identity_available"] is False
    assert result["candidate_membership_rows"] == 0


def test_wrong_month_must_fail(tmp_path):
    path = tmp_path / "wrong.xlsx"
    _xlsx(path, movement_date="02-11-24")
    with pytest.raises(history.HistoricalRawError, match="Reporte equivocado"):
        history.profile_download(path, expected_month=date(2024, 12, 31))


def test_resume_rejects_modified_or_missing_manifest(tmp_path):
    month = date(2024, 12, 31)
    output, manifest = history.month_paths(tmp_path, month)
    output.parent.mkdir(parents=True)
    _xlsx(output)
    with pytest.raises(history.HistoricalRawError, match="incompletos"):
        history.resumable(output, manifest)
    manifest.write_text(json.dumps({"sha256": history.file_sha256(output)}))
    assert history.resumable(output, manifest)
    output.write_bytes(b"changed")
    with pytest.raises(history.HistoricalRawError, match="SHA256 diferente"):
        history.resumable(output, manifest)


def test_dry_run_does_not_login_or_write(tmp_path, monkeypatch):
    def forbidden():
        raise AssertionError("No debe conectar sin --execute")

    monkeypatch.setattr(history, "create_app", forbidden)
    result = history.run_backfill(
        start=date(2024, 12, 1),
        end=date(2024, 12, 1),
        output_root=tmp_path,
        execute=False,
    )
    assert result == {"planned": 1, "downloaded": 0, "skipped": 0, "errors": 0}
    assert not list(tmp_path.iterdir())


def test_approved_download_preserves_raw_and_resumes(tmp_path, monkeypatch):
    source = tmp_path / "sample.xlsx"
    _xlsx(source)
    app = Flask("qa")
    monkeypatch.setattr(history, "create_app", lambda: app)
    monkeypatch.setattr(history.gasca, "_resolve_runtime_config", lambda: object())
    monkeypatch.setattr(
        history.gasca, "_authenticated_page",
        lambda runtime: _fake_page(),
    )
    downloaded = []

    def fake_download(page, *, runtime, end, target):
        downloaded.append(end)
        target.write_bytes(source.read_bytes())

    monkeypatch.setattr(history, "download_month", fake_download)
    root = tmp_path / "reports"
    kwargs = dict(
        start=date(2024, 12, 1), end=date(2024, 12, 1),
        output_root=root, execute=True, sleep_seconds=2.0,
    )
    first = history.run_backfill(**kwargs)
    assert first["downloaded"] == 1
    output, manifest = history.month_paths(root, date(2024, 12, 31))
    assert output.read_bytes() == source.read_bytes()
    record = json.loads(manifest.read_text())
    assert record["state"] == "RAW_ONLY_NON_CANONICAL"
    assert record["rows_with_idsocio"] == 2
    assert record["sha256"] == history.file_sha256(source)
    second = history.run_backfill(**kwargs)
    assert second["skipped"] == 1
    assert downloaded == [date(2024, 12, 31)]


@contextmanager
def _fake_page():
    yield object()
