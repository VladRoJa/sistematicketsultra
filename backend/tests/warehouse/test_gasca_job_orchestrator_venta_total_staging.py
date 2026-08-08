from datetime import date

import pytest
from flask import Flask

import app.warehouse.services.gasca_job_orchestrator as service


def _build_app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app


def test_run_gasca_report_job_propagates_non_canonical_to_venta_total():
    app = _build_app()
    captured = {}

    def fake_extractor(**kwargs):
        captured["extractor"] = dict(kwargs)

        return {
            "report_type_key": "venta_total",
            "original_filename": "venta_total_2026_07_31.xlsx",
            "content_type": (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            "file_bytes": b"fake-xlsx",
            "metadata": {
                "date_from": "2026-07-01",
                "date_to": "2026-07-31",
            },
        }

    def fake_upload_creator(**kwargs):
        captured["upload"] = dict(kwargs)

        return {
            "warehouse_upload_id": 501,
            "upload_status": "created",
        }

    def fake_venta_total_ingestor(**kwargs):
        captured["ingestor"] = dict(kwargs)

        return {
            "status": "ingested",
            "snapshot_id": 777,
            "metadata": {
                "is_canonical": False,
            },
        }

    app.config["WAREHOUSE_GASCA_EXTRACTOR"] = fake_extractor
    app.config["WAREHOUSE_INTERNAL_UPLOAD_CREATOR"] = (
        fake_upload_creator
    )
    app.config["WAREHOUSE_VENTA_TOTAL_INGESTOR"] = (
        fake_venta_total_ingestor
    )

    with app.app_context():
        result = service.run_gasca_report_job(
            report_type_key="venta_total",
            run_mode="manual_retry",
            snapshot_kind="daily",
            requested_by="admin_test",
            trigger_source="manual_canonical_close",
            target_business_date=date(2026, 7, 31),
            force_ingestion=True,
            force_non_canonical=True,
        )

    assert captured["extractor"]["target_business_date"] == date(
        2026,
        7,
        31,
    )

    assert captured["ingestor"] == {
        "warehouse_upload_id": 501,
        "snapshot_kind": "daily",
        "requested_by": "admin_test",
        "ingestion_source": "manual_canonical_close",
        "force_non_canonical": True,
    }

    assert result["report_type_key"] == "venta_total"
    assert result["snapshot_id"] == 777
    assert result["ingestion_status"] == "ingested"
    assert result["force_non_canonical"] is True
    assert result["target_business_date"] == "2026-07-31"


def test_force_non_canonical_rejected_for_non_venta_total():
    app = _build_app()

    with app.app_context():
        with pytest.raises(
            ValueError,
            match="force_non_canonical solo aplica",
        ):
            service.run_gasca_report_job(
                report_type_key="reporte_direccion",
                run_mode="manual_retry",
                snapshot_kind="daily",
                requested_by="admin_test",
                trigger_source="test",
                force_ingestion=True,
                force_non_canonical=True,
            )
