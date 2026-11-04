"""KPI Desempeño: historical Gasca exports and manual Warehouse ingestion."""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

import pytest
from flask import Flask
from openpyxl import Workbook

from app.warehouse.services.kpi_desempeno_parser import (
    EXPECTED_KPI_DESEMPENO_COLUMNS,
    parse_kpi_desempeno_xlsx,
)
from app.warehouse.services.kpi_desempeno_ingestion_service import (
    KpiDesempenoIngestionError,
    ingest_kpi_desempeno_upload,
)
import app.warehouse.services.kpi_desempeno_ingestion_service as ingestion
from app.warehouse.services.warehouse_manual_ingestion_dispatcher import (
    dispatch_manual_structured_ingestion,
)


def _gasca_xlsx(cutoff: str, *, title: bool) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "Sheet1"
    if title:
        sheet.append([f"KPIs Desempeño (Corte: {cutoff})"])
    sheet.append(list(EXPECTED_KPI_DESEMPENO_COLUMNS))

    month_end = cutoff.startswith("30/09")
    socios = 455 if month_end else 722
    initial = 301 if month_end else 458
    new = 156 if month_end else 267

    sheet.append(["METEPEC", initial, new, 0, 0, 0, socios, 0, socios - 1])
    sheet.append(["LA VIGA", 100, 20, 0, 0, 0, 120, 0, 119])
    sheet.append(["Totales :", 0, 0, 0, 0, 0, 0, 0, 0])
    if title:
        sheet.append(["Reporte generado: 04-11-2026 10:43 a. m."])
    stream = BytesIO()
    book.save(stream)
    book.close()
    return stream.getvalue()


@pytest.mark.parametrize(
    ("cutoff", "expected_date", "expected_socios"),
    [
        ("30/09/2025", "2025-09-30", 455),
        ("31/10/2025", "2025-10-31", 722),
    ],
)
def test_gasca_titled_historical_exports(cutoff, expected_date, expected_socios):
    result = parse_kpi_desempeno_xlsx(
        file_bytes=_gasca_xlsx(cutoff, title=True)
    )
    assert result.report_cutoff_date == expected_date
    assert result.row_count == 1
    assert result.skipped_rows == 3
    assert result.rows[0].sucursal_nombre == "METEPEC"
    assert result.rows[0].socios_activos_del_mes == expected_socios


def test_normal_header_file_remains_compatible():
    result = parse_kpi_desempeno_xlsx(
        file_bytes=_gasca_xlsx("30/09/2025", title=False)
    )
    assert result.report_cutoff_date is None
    assert result.row_count == 1
    assert result.rows[0].socios_activos_del_mes == 455


def test_manual_warehouse_routes_kpi_to_registered_ingestor():
    app = Flask(__name__)
    calls = []
    app.config["WAREHOUSE_UPLOAD_LOADER"] = (
        lambda warehouse_upload_id: {
            "warehouse_upload_id": warehouse_upload_id,
            "report_type_key": "kpi_desempeno",
            "cutoff_date": "2025-09-30",
        }
    )

    def fake_ingestor(**kwargs):
        calls.append(kwargs)
        return {
            "status": "ingested",
            "snapshot_id": 3001,
            "business_date": "2025-09-30",
            "is_canonical": True,
            "row_count_valid": 26,
        }

    app.config["WAREHOUSE_KPI_DESEMPENO_INGESTOR"] = fake_ingestor

    with app.app_context():
        result = dispatch_manual_structured_ingestion(
            warehouse_upload_id=123,
            requested_by="ADMICORP",
            ingestion_source="manual_route",
        )

    assert result["ingestion_status"] == "ingested"
    assert result["snapshot_kind"] == "daily"
    assert result["structured_result"]["snapshot_id"] == 3001
    assert calls == [{
        "warehouse_upload_id": 123,
        "requested_by": "ADMICORP",
        "ingestion_source": "manual_route",
        "snapshot_kind": "daily",
    }]


def test_ingestion_rejects_wrong_manual_cutoff_before_publication(monkeypatch):
    monkeypatch.setattr(
        ingestion,
        "_load_upload_document",
        lambda **_kwargs: SimpleNamespace(cutoff_date="2025-10-31"),
    )
    monkeypatch.setattr(
        ingestion,
        "_parse_upload_document",
        lambda **_kwargs: {
            "report_cutoff_date": "2025-09-30",
            "rows": [{"sucursal_nombre": "METEPEC"}],
        },
    )

    def unexpected_repo():
        raise AssertionError("Repository must not be called for an invalid cutoff")

    monkeypatch.setattr(ingestion, "_resolve_repository", unexpected_repo)
    with pytest.raises(KpiDesempenoIngestionError, match="no coincide"):
        ingest_kpi_desempeno_upload(
            warehouse_upload_id=123, snapshot_kind="daily"
        )
