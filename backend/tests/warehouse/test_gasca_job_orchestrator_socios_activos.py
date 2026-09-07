from datetime import date

import pytest
from flask import Flask

import app.warehouse.services.gasca_job_orchestrator as service


def _build_app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app


def test_socios_activos_runs_current_daily_ingestion():
    app = _build_app()
    captured = {}

    def fake_extractor(**kwargs):
        captured["extractor"] = dict(kwargs)
        return {
            "report_type_key": "socios_activos",
            "original_filename": "socios_activos.xlsx",
            "file_bytes": b"fake-xlsx",
            "metadata": {"cutoff_date": "2026-09-07"},
        }

    def fake_upload_creator(**kwargs):
        return {"warehouse_upload_id": 701}

    def fake_ingestor(**kwargs):
        captured["ingestor"] = dict(kwargs)
        return {
            "status": "ingested",
            "snapshot_id": 1701,
            "cutoff_date": "2026-09-07",
            "row_count_valid": 36000,
        }

    app.config["WAREHOUSE_GASCA_EXTRACTOR"] = fake_extractor
    app.config["WAREHOUSE_INTERNAL_UPLOAD_CREATOR"] = fake_upload_creator
    app.config["WAREHOUSE_SOCIOS_ACTIVOS_INGESTOR"] = fake_ingestor

    with app.app_context():
        result = service.run_gasca_report_job(
            report_type_key="socios_activos",
            run_mode="scheduled_daily",
            snapshot_kind="daily",
            requested_by="scheduler_test",
            trigger_source="test",
            target_business_date=date(2026, 9, 7),
        )

    assert captured["extractor"]["target_business_date"] == date(2026, 9, 7)
    assert captured["ingestor"] == {
        "warehouse_upload_id": 701,
        "requested_by": "scheduler_test",
        "ingestion_source": "test",
    }
    assert result["ingestion_status"] == "ingested"
    assert result["snapshot_id"] == 1701
    assert result["ingestion_metadata"]["row_count_valid"] == 36000


def test_socios_activos_rejects_manual_backfill():
    app = _build_app()
    with app.app_context(), pytest.raises(ValueError, match="combinación"):
        service.run_gasca_report_job(
            report_type_key="socios_activos",
            run_mode="manual_backfill",
            snapshot_kind="daily",
            target_business_date=date(2026, 9, 7),
        )
