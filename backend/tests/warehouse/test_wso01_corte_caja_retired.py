"""WSO-01: Corte de Caja has been retired from Gasca job orchestration."""

import pytest
from flask import Flask

from app.warehouse.services import gasca_job_orchestrator


@pytest.mark.parametrize("run_mode", ["scheduled_daily", "manual_backfill", "manual_retry"])
def test_corte_caja_is_rejected_before_extraction_or_upload(run_mode):
    app = Flask(__name__)
    calls = []

    def forbidden_hook(**kwargs):
        calls.append(kwargs)
        raise AssertionError("A retired report must not invoke Warehouse hooks")

    app.config["WAREHOUSE_GASCA_EXTRACTOR"] = forbidden_hook
    app.config["WAREHOUSE_INTERNAL_UPLOAD_CREATOR"] = forbidden_hook

    with app.app_context(), pytest.raises(ValueError, match="report_type_key"):
        gasca_job_orchestrator.run_gasca_report_job(
            report_type_key="corte_caja",
            run_mode=run_mode,
            snapshot_kind="daily",
            force_ingestion=True,
        )

    assert calls == []
    assert "corte_caja" not in gasca_job_orchestrator.SUPPORTED_REPORT_TYPES
