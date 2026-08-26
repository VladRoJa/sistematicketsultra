from __future__ import annotations

from datetime import date, datetime, timezone

from flask import Flask
import pytest

import app.warehouse.services.socios_vencidos_ingestion_service as ingestion


CAPTURED_AT = datetime(2026, 8, 24, 8, 0, tzinfo=timezone.utc)


def _app() -> Flask:
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app


def _upload(**overrides):
    payload = {
        "warehouse_upload_id": 101,
        "report_type_key": "socios_vencidos",
        "original_filename": "socios-vencidos-ficticio.xlsx",
        "file_bytes": b"xlsx-ficticio",
        "captured_at": CAPTURED_AT,
        "period_type": "rango",
        "date_from": date(2026, 8, 23),
        "date_to": date(2026, 8, 23),
        "metadata": {"source": "test"},
    }
    payload.update(overrides)
    return payload


def test_ingestion_coordinates_loader_parser_and_range_repository():
    app = _app()
    parser_calls = []
    repository_calls = []

    app.config["WAREHOUSE_UPLOAD_LOADER"] = (
        lambda warehouse_upload_id: _upload(
            warehouse_upload_id=warehouse_upload_id
        )
    )

    def parser(**kwargs):
        parser_calls.append(kwargs)
        return {
            "rows": [],
            "row_count_detected": 0,
            "row_count_valid": 0,
            "row_count_rejected": 0,
            "data_quality_counts": {
                "invalid_edad": 10,
                "missing_edad": 2,
            },
        }

    def repository(**kwargs):
        repository_calls.append(kwargs)
        return {
            "status": "ingested",
            "snapshot_id": 91,
            "row_count_valid": 0,
            "row_count_rejected": 0,
            "rows_inserted": 0,
        }

    app.config["WAREHOUSE_SOCIOS_VENCIDOS_PARSER"] = parser
    app.config["WAREHOUSE_SOCIOS_VENCIDOS_REPOSITORY"] = repository

    with app.app_context():
        result = ingestion.ingest_socios_vencidos_upload(
            warehouse_upload_id=101,
            requested_by="test",
            ingestion_source="test_suite",
        )

    assert result["status"] == "ingested"
    assert result["data_quality_counts"] == {
        "invalid_edad": 10,
        "missing_edad": 2,
    }
    assert parser_calls[0]["file_bytes"] == b"xlsx-ficticio"
    assert repository_calls[0]["date_from"] == date(2026, 8, 23)
    assert repository_calls[0]["date_to"] == date(2026, 8, 23)
    assert "business_date" not in repository_calls[0]
    assert "snapshot_kind" not in repository_calls[0]


def test_ingestion_rejects_wrong_report_type():
    app = _app()
    app.config["WAREHOUSE_UPLOAD_LOADER"] = (
        lambda **_: _upload(report_type_key="venta_total")
    )

    with app.app_context():
        with pytest.raises(
            ingestion.SociosVencidosUploadLoadError,
            match="no corresponde",
        ):
            ingestion.ingest_socios_vencidos_upload(
                warehouse_upload_id=101
            )


def test_ingestion_rejects_invalid_range():
    app = _app()
    app.config["WAREHOUSE_UPLOAD_LOADER"] = (
        lambda **_: _upload(
            date_from=date(2026, 8, 24),
            date_to=date(2026, 8, 23),
        )
    )

    with app.app_context():
        with pytest.raises(
            ingestion.SociosVencidosUploadLoadError,
            match="posterior",
        ):
            ingestion.ingest_socios_vencidos_upload(
                warehouse_upload_id=101
            )


def test_ingestion_wraps_parser_failure():
    app = _app()
    app.config["WAREHOUSE_UPLOAD_LOADER"] = lambda **_: _upload()

    def failing_parser(**_):
        raise ValueError("xlsx ficticio inválido")

    app.config["WAREHOUSE_SOCIOS_VENCIDOS_PARSER"] = failing_parser

    with app.app_context():
        with pytest.raises(
            ingestion.SociosVencidosParseError,
            match="Falló el parser",
        ):
            ingestion.ingest_socios_vencidos_upload(
                warehouse_upload_id=101
            )
