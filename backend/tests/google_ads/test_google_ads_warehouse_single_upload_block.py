"""Guard generic Warehouse uploads against bypassing paired Google Ads M6 ingestion.

No database, credentials, document storage or real file writes are involved.
"""
from __future__ import annotations

from io import BytesIO

import pytest
from flask import Flask

from app.routes import warehouse_routes as routes


@pytest.mark.parametrize("report_type_key", [
    "google_ads_campaign_daily",
    "google_ads_ad_group_daily",
])
def test_single_google_ads_upload_fails_before_raw_write(monkeypatch, report_type_key):
    app = Flask(__name__)
    touched = []

    monkeypatch.setattr(routes, "require_warehouse_upload", lambda: None)
    monkeypatch.setattr(routes, "_get_current_user_id", lambda: 47)
    monkeypatch.setattr(
        routes, "create_warehouse_document_upload",
        lambda **kwargs: touched.append(kwargs),
    )
    # Even if the dispatcher were configured, no legacy ingestion should run.
    app.config["WAREHOUSE_MANUAL_INGESTION_DISPATCHER"] = (
        lambda **kwargs: touched.append(kwargs)
    )

    with app.test_request_context(
        "/api/warehouse/uploads",
        method="POST",
        data={
            "report_type_key": report_type_key,
            "file": (BytesIO(b"dummy-ads-data"), "report.xlsx"),
        },
        content_type="multipart/form-data",
    ):
        response, status = routes.warehouse_create_upload.__wrapped__()

    assert status == 409
    assert response.get_json()["code"] == "GOOGLE_ADS_M6_PAIRED_UPLOAD_REQUIRED"
    assert touched == []


def test_other_warehouse_uploads_keep_their_existing_path(monkeypatch):
    app = Flask(__name__)
    observed = []

    def upload(**kwargs):
        observed.append(kwargs["report_type_key"])
        return {
            "upload_id": 991, "filename": "report.xlsx",
            "stored_filename": "stored.xlsx", "display_filename": "report.xlsx",
            "stored_path": "qa", "file_size_bytes": 4,
            "file_hash_sha256": "a" * 64, "report_type_key": "venta_total",
            "report_type_id": 1, "family_id": 1, "source_id": 1,
            "operational_role_id": 1, "period_type": "diario",
            "cutoff_date": "2026-10-13", "date_from": "2026-10-13",
            "date_to": "2026-10-13", "duplicate_detected": False,
            "duplicate_upload_id": None,
        }

    monkeypatch.setattr(routes, "require_warehouse_upload", lambda: None)
    monkeypatch.setattr(routes, "_get_current_user_id", lambda: 47)
    monkeypatch.setattr(routes, "create_warehouse_document_upload", upload)

    with app.test_request_context(
        "/api/warehouse/uploads",
        method="POST",
        data={"report_type_key": "venta_total", "file": (BytesIO(b"data"), "report.xlsx")},
        content_type="multipart/form-data",
    ):
        response, status = routes.warehouse_create_upload.__wrapped__()

    assert status == 201
    assert response.get_json()["report_type_key"] == "venta_total"
    assert observed == ["venta_total"]
