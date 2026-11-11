"""Synthetic coverage: generated cobranza files to governed Campaign V2."""
from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

import pytest
from openpyxl import Workbook, load_workbook

from app.warehouse.jobs.cobranza_iventas_preparation import (
    CobranzaCampaignPreparationError,
    build_import_bytes,
)
from app.services.marketing_campaign_v2_cobranza_send_service import (
    is_prepared_cobranza_campaign,
)


def _artifact(tmp_path, *, branch, rows):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Socio", "Teléfono", "Estatus"])
    for row in rows:
        sheet.append(row)
    path = tmp_path / (branch + ".xlsx")
    workbook.save(path)
    return {"path": str(path), "sucursal_raw": branch, "rows_count": len(rows)}


def _rows(result):
    workbook = load_workbook(BytesIO(result), read_only=True, data_only=True)
    try:
        return list(workbook.active.values)
    finally:
        workbook.close()


def test_generated_files_become_two_column_audience(tmp_path):
    artifacts = [
        _artifact(tmp_path, branch="VILLA VERDE", rows=[
            [1, "6861234567", "Rechazado"],
            [2, "6861234567", "Rechazado"],
            [3, "123", "Rechazado"],
        ]),
        _artifact(tmp_path, branch="SAN LUIS", rows=[
            [4, "6531234567", "Rechazado"],
        ]),
    ]
    payload, count = build_import_bytes(artifacts)
    assert count == 2
    assert _rows(payload) == [
        ("sucursal", "telefono"),
        ("SAN LUIS", "6531234567"),
        ("VILLA VERDE", "6861234567"),
    ]


def test_ambiguous_phone_across_branches_is_not_sent(tmp_path):
    files = [
        _artifact(tmp_path, branch="VILLA VERDE", rows=[[1, "6861234567", "Rechazado"]]),
        _artifact(tmp_path, branch="SAN LUIS", rows=[[2, "6861234567", "Rechazado"]]),
    ]
    with pytest.raises(CobranzaCampaignPreparationError, match="validos"):
        build_import_bytes(files)


def test_missing_phone_column_does_not_guess(tmp_path):
    workbook = Workbook()
    workbook.active.append(["Socio", "Correo", "Estatus"])
    workbook.active.append([1, "correo@example.test", "Rechazado"])
    path = tmp_path / "sin_telefono.xlsx"
    workbook.save(path)
    with pytest.raises(CobranzaCampaignPreparationError, match="columna de telefono"):
        build_import_bytes([{"path": str(path), "sucursal_raw": "SAN LUIS"}])


def test_only_provenance_marked_campaigns_can_send():
    source = SimpleNamespace(
        source="EXCEL_IMPORT",
        name="COBRANZA RECURRENTE RECHAZADOS - 2026-11-10",
        audience_definition_json={"source_metadata": {
            "automation_job": "cobranza_recurrente_rechazados",
            "business_date": "2026-11-10",
            "template_id_at_freeze": 42,
        }},
    )
    assert is_prepared_cobranza_campaign(campaign=source)
    source.audience_definition_json["source_metadata"]["automation_job"] = "manual"
    assert not is_prepared_cobranza_campaign(campaign=source)
