"""Legacy Gasca KPI disk fallback must respect an explicit business date.

Synthetic-only: no browser, Gasca credentials, database or Warehouse writes.
"""
from datetime import date, datetime, timedelta, timezone
import os

from flask import Flask
import pytest

from app.warehouse.services import gasca_script_bridge as bridge
from app.warehouse.services.gasca_job_orchestrator import GascaProducerError


@pytest.mark.parametrize(("report_type", "prefix", "trigger"), [
    ("kpi_desempeno", "kpi_desempeno_", "manual_retry"),
    ("kpi_ventas_nuevos_socios", "kpi_ventas_nuevos_socios_",
     "track_daily_pipeline_recent_disk_only"),
])
def test_wrong_date_never_wins_by_newer_mtime(tmp_path, report_type, prefix, trigger):
    now = datetime.now(timezone.utc)
    today = date(2026, 10, 20)
    correct = tmp_path / f"{prefix}2026-10-20_13-20.xlsx"
    wrong = tmp_path / f"{prefix}2026-10-19_13-21.xlsx"
    correct.write_bytes(b"synthetic-correct-day")
    wrong.write_bytes(b"synthetic-wrong-day")
    os.utime(correct, (now.timestamp() - 60, now.timestamp() - 60))
    os.utime(wrong, (now.timestamp(), now.timestamp()))

    app = Flask("synthetic-gasca-day-filter")
    app.config.update(
        WAREHOUSE_GASCA_SCRIPT_OUTPUT_DIRS={report_type: str(tmp_path)},
        WAREHOUSE_GASCA_SCRIPT_RUNNER=lambda **kwargs: None,
    )
    with app.app_context():
        artifact = bridge.extract_with_gasca_script(
            report_type_key=report_type,
            run_mode="manual_retry",
            snapshot_kind="daily",
            target_business_date=today,
            requested_at=now - timedelta(minutes=3),
            trigger_source=trigger,
        )
    assert artifact.file_path == str(correct)
    assert artifact.metadata["bridge_source"] == "recent_disk_scan"


def test_missing_requested_day_fails_instead_of_reusing_wrong_day(tmp_path):
    now = datetime.now(timezone.utc)
    wrong = tmp_path / "kpi_desempeno_2026-10-19_13-20.xlsx"
    wrong.write_bytes(b"synthetic-wrong-day")
    os.utime(wrong, (now.timestamp(), now.timestamp()))
    app = Flask("synthetic-gasca-missing-day")
    app.config.update(
        WAREHOUSE_GASCA_SCRIPT_OUTPUT_DIRS={"kpi_desempeno": str(tmp_path)},
        WAREHOUSE_GASCA_SCRIPT_RUNNER=lambda **kwargs: None,
    )
    with app.app_context(), pytest.raises(GascaProducerError, match="tampoco se encontró"):
        bridge.extract_with_gasca_script(
            report_type_key="kpi_desempeno",
            run_mode="manual_retry",
            snapshot_kind="daily",
            target_business_date=date(2026, 10, 20),
            requested_at=now - timedelta(minutes=3),
        )


def test_other_report_types_keep_legacy_selection_behavior(tmp_path):
    now = datetime.now(timezone.utc)
    file = tmp_path / "ingresos_2026-10-19_13-20.xlsx"
    file.write_bytes(b"synthetic-direccion")
    os.utime(file, (now.timestamp(), now.timestamp()))
    app = Flask("synthetic-gasca-other-type")
    app.config.update(
        WAREHOUSE_GASCA_SCRIPT_OUTPUT_DIRS={"reporte_direccion": str(tmp_path)},
        WAREHOUSE_GASCA_SCRIPT_RUNNER=lambda **kwargs: None,
    )
    with app.app_context():
        artifact = bridge.extract_with_gasca_script(
            report_type_key="reporte_direccion",
            run_mode="manual_retry",
            snapshot_kind="daily",
            target_business_date=date(2026, 10, 20),
            requested_at=now - timedelta(minutes=3),
        )
    assert artifact.file_path == str(file)
