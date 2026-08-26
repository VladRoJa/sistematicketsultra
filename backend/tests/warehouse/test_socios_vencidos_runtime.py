from __future__ import annotations

from flask import Flask

from app.warehouse import register_warehouse_runtime_hooks
from app.warehouse.services.warehouse_manual_ingestion_dispatcher import (
    dispatch_manual_structured_ingestion,
)


def test_runtime_registers_socios_vencidos_hooks():
    app = Flask(__name__)

    register_warehouse_runtime_hooks(app)

    assert callable(app.config["WAREHOUSE_SOCIOS_VENCIDOS_PARSER"])
    assert callable(app.config["WAREHOUSE_SOCIOS_VENCIDOS_REPOSITORY"])
    assert callable(app.config["WAREHOUSE_SOCIOS_VENCIDOS_INGESTOR"])
    assert app.extensions["warehouse_runtime_hooks"][
        "socios_vencidos_ingestor"
    ] is True


def test_manual_dispatcher_routes_range_report_without_snapshot_kind():
    app = Flask(__name__)
    ingestor_calls = []
    app.config["WAREHOUSE_UPLOAD_LOADER"] = (
        lambda warehouse_upload_id: {
            "warehouse_upload_id": warehouse_upload_id,
            "report_type_key": "socios_vencidos",
        }
    )

    def ingestor(**kwargs):
        ingestor_calls.append(kwargs)
        return {"status": "ingested", "snapshot_id": 91}

    app.config["WAREHOUSE_SOCIOS_VENCIDOS_INGESTOR"] = ingestor

    with app.app_context():
        result = dispatch_manual_structured_ingestion(
            warehouse_upload_id=101,
            requested_by="test",
            ingestion_source="test_suite",
        )

    assert result["ingestion_status"] == "ingested"
    assert result["report_type_key"] == "socios_vencidos"
    assert "snapshot_kind" not in result
    assert "snapshot_kind" not in ingestor_calls[0]
