"""WSO-01: Corte de Caja has been retired from Gasca job orchestration."""

from io import BytesIO

import pytest
from flask import Flask

from app.warehouse.services import gasca_job_orchestrator
from app.routes import warehouse_routes


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


def test_corte_caja_manual_upload_returns_gone_before_storage(monkeypatch):
    app = Flask(__name__)
    writes = []
    monkeypatch.setattr(warehouse_routes, "require_warehouse_upload", lambda: None)
    monkeypatch.setattr(warehouse_routes, "_get_current_user_id", lambda: 47)
    monkeypatch.setattr(
        warehouse_routes,
        "create_warehouse_document_upload",
        lambda **kwargs: writes.append(kwargs),
    )
    with app.test_request_context(
        "/api/warehouse/uploads",
        method="POST",
        data={
            "report_type_key": "corte_caja",
            "file": (BytesIO(b"dummy"), "corte.xlsx"),
        },
        content_type="multipart/form-data",
    ):
        response, code = warehouse_routes.warehouse_create_upload.__wrapped__()

    assert code == 410
    assert response.get_json()["code"] == "WAREHOUSE_REPORT_RETIRED"
    assert writes == []
