from datetime import date
from unittest.mock import patch

import pytest

from app.warehouse.jobs.reporte_direccion_daily_capture_job import (
    ReporteDireccionBusinessDateMismatchError,
    run_job,
)


def _fake_gasca_result():
    return {
        "report_type_key": "reporte_direccion",
        "job_status": "ingested",
        "ingestion_status": "ingested",
        "warehouse_upload_id": 12345,
        "snapshot_id": 67890,
    }


def test_run_job_solicita_solo_reporte_direccion():
    captured = {}
    business_date = date(2026, 9, 5)

    def fake_run_gasca_report_job(**kwargs):
        captured.update(kwargs)
        return _fake_gasca_result()

    with (
        patch(
            "app.warehouse.jobs.reporte_direccion_daily_capture_job."
            "run_gasca_report_job",
            side_effect=fake_run_gasca_report_job,
        ),
        patch(
            "app.warehouse.jobs.reporte_direccion_daily_capture_job."
            "_load_persisted_business_date",
            return_value=business_date,
        ),
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


def test_run_job_falla_si_business_date_persistida_no_coincide():
    requested_date = date(2026, 9, 5)
    persisted_date = date(2026, 9, 6)

    with (
        patch(
            "app.warehouse.jobs.reporte_direccion_daily_capture_job."
            "run_gasca_report_job",
            return_value=_fake_gasca_result(),
        ),
        patch(
            "app.warehouse.jobs.reporte_direccion_daily_capture_job."
            "_load_persisted_business_date",
            return_value=persisted_date,
        ),
    ):
        with pytest.raises(
            ReporteDireccionBusinessDateMismatchError
        ) as exc_info:
            run_job(
                business_date=requested_date,
            )

    message = str(exc_info.value)

    assert "expected=2026-09-05" in message
    assert "actual=2026-09-06" in message
    assert "snapshot_id=67890" in message
