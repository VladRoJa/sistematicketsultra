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


def test_gasca_generated_xlsx_round_trip_pilot_one_branch(tmp_path):
    """Real Gasca splitter -> campaign importer shape, never dispatches."""
    from app.warehouse.jobs._cobranza_recurrente_rechazados_xlsx import procesar_archivo

    raw = Workbook()
    ws = raw.active
    ws.append(["REPORTE GASCA", *[""] * 11])
    headers = [
        "ID", "Socio", "Concepto", "Fecha", "Cargo", "Clave",
        "Sucursal", "Teléfono", "Estatus", "Observación", "Referencia", "Eliminar",
    ]
    ws.append(headers)
    ws.append([1, "Uno", "", "", "", "", "AZAHARES CUL", "6861234567", "Rechazado", "", "", "X"])
    ws.append([2, "Dos", "", "", "", "", "AZAHARES CUL", "6867654321", "Aprobado", "", "", "X"])
    ws.append([3, "Tres", "", "", "", "", "AZAHARES CUL", "6861234567", "Rechazado", "", "", "X"])
    ws.append(["Reporte generado", *[""] * 11])
    source = tmp_path / "gasca_raw.xlsx"
    raw.save(source)
    outcome = procesar_archivo(source, tmp_path / "por_sucursal")
    assert outcome["total_files"] == 1
    assert outcome["total_rows"] == 2
    payload, count = build_import_bytes(outcome["artifacts"])
    assert count == 1
    assert _rows(payload) == [
        ("sucursal", "telefono"),
        ("AZAHARES CUL", "6861234567"),
    ]
