from datetime import date
from unittest.mock import patch

from app.warehouse.jobs.reporte_direccion_daily_capture_job import (
    run_job,
)


def test_run_job_solicita_solo_reporte_direccion():
    captured = {}

    def fake_run_gasca_report_job(**kwargs):
        captured.update(kwargs)

        return {
            "report_type_key": "reporte_direccion",
            "job_status": "ingested",
            "ingestion_status": "ingested",
            "warehouse_upload_id": 12345,
            "snapshot_id": 67890,
        }

    business_date = date(2026, 9, 5)

    with patch(
        "app.warehouse.jobs.reporte_direccion_daily_capture_job."
        "run_gasca_report_job",
        side_effect=fake_run_gasca_report_job,
    ):
        result = run_job(
            business_date=business_date,
        )

    assert captured == {
        "report_type_key": "reporte_direccion",
        "run_mode": "manual_retry",
        "snapshot_kind": "daily",
        "requested_by": "reports_scheduler",
        "trigger_source": "reporte_direccion_daily_capture",
        "target_business_date": business_date,
        "report_types": (
            "reporte_direccion",
        ),
        "force_ingestion": True,
    }

    assert result["status"] == "completed"
    assert result["business_date"] == "2026-09-05"
    assert result["report_type_key"] == "reporte_direccion"
    assert result["warehouse_upload_id"] == 12345
    assert result["snapshot_id"] == 67890
    assert result["ingestion_status"] == "ingested"
