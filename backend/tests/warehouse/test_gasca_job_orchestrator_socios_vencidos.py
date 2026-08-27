from datetime import date

import pytest
from flask import Flask

import app.warehouse.services.gasca_job_orchestrator as service


def _build_app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app


def test_socios_vencidos_propagates_range_and_ingestion_metadata():
    app = _build_app()
    captured = {}

    def fake_extractor(**kwargs):
        captured["extractor"] = dict(kwargs)
        return {
            "report_type_key": "socios_vencidos",
            "original_filename": "socios_vencidos_2026_08.xlsx",
            "file_bytes": b"fake-xlsx",
        }

    def fake_upload_creator(**kwargs):
        captured["upload"] = dict(kwargs)
        return {"warehouse_upload_id": 501}

    def fake_ingestor(**kwargs):
        captured["ingestor"] = dict(kwargs)
        return {
            "status": "ingested",
            "snapshot_id": 91,
            "cartera_inserted": 20,
            "cartera_updated": 2,
            "cartera_existing": 3,
            "cleanup_warning": None,
        }

    app.config["WAREHOUSE_GASCA_EXTRACTOR"] = fake_extractor
    app.config["WAREHOUSE_INTERNAL_UPLOAD_CREATOR"] = (
        fake_upload_creator
    )
    app.config["WAREHOUSE_SOCIOS_VENCIDOS_INGESTOR"] = fake_ingestor

    with app.app_context():
        result = service.run_gasca_report_job(
            report_type_key="socios_vencidos",
            run_mode="manual_backfill",
            snapshot_kind="daily",
            requested_by="admin_test",
            trigger_source="test",
            date_from=date(2026, 8, 1),
            date_to=date(2026, 8, 31),
        )

    assert captured["extractor"]["date_from"] == date(2026, 8, 1)
    assert captured["extractor"]["date_to"] == date(2026, 8, 31)
    assert captured["ingestor"] == {
        "warehouse_upload_id": 501,
        "requested_by": "admin_test",
        "ingestion_source": "test",
    }
    assert result["date_from"] == "2026-08-01"
    assert result["date_to"] == "2026-08-31"
    assert result["ingestion_metadata"]["cartera_inserted"] == 20
    assert result["ingestion_metadata"]["cartera_existing"] == 3


@pytest.mark.parametrize(
    "date_from,date_to",
    [
        (None, date(2026, 8, 31)),
        (date(2026, 8, 1), None),
        (date(2026, 9, 1), date(2026, 8, 31)),
    ],
)
def test_socios_vencidos_rejects_missing_or_inverted_range(
    date_from,
    date_to,
):
    app = _build_app()

    with app.app_context(), pytest.raises(ValueError):
        service.run_gasca_report_job(
            report_type_key="socios_vencidos",
            run_mode="manual_backfill",
            snapshot_kind="daily",
            date_from=date_from,
            date_to=date_to,
        )
