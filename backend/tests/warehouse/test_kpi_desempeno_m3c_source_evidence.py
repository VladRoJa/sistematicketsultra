"""M3-C read-only source-evidence labels never authorize an update."""
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.models.warehouse import WarehouseUploadORM
from app.warehouse.services import kpi_desempeno_m3c_source_evidence_service as evidence


DAY = date(2026, 10, 20)


def _mock_upload(monkeypatch, details, *, audit_present=True, source_status="ACTIVE",
                 report_key="kpi_desempeno", period_type="diario", cutoff=DAY,
                 file_deleted=False):
    upload = SimpleNamespace(
        id=42,
        status=source_status,
        source_file_deleted_at=DAY if file_deleted else None,
        period_type=period_type,
        cutoff_date=cutoff,
        report_type=SimpleNamespace(key=report_key),
        uploaded_by_user_id=900,
    )
    reads = {"uploads": 0, "audits": 0, "filter": []}
    def get(model, identifier):
        assert model is WarehouseUploadORM
        assert identifier == 42
        reads["uploads"] += 1
        return upload

    class AuditQuery:
        def filter_by(self, **kwargs):
            reads["filter"].append(kwargs)
            return self

        def first(self):
            reads["audits"] += 1
            return SimpleNamespace(details=details) if audit_present else None

    monkeypatch.setattr(evidence.db.session, "get", get)
    monkeypatch.setattr(evidence.WarehouseAuditLogORM, "query", AuditQuery())
    return reads


@pytest.mark.parametrize(("method", "status"), [
    ("recent_disk_scan", evidence.DISK_FALLBACK_UNVERIFIED),
    ("direct_path_result", evidence.DIRECT_ARTIFACT_UNVERIFIED),
    ("dict_result", evidence.DIRECT_ARTIFACT_UNVERIFIED),
    ("single_report_runner", evidence.DIRECT_ARTIFACT_UNVERIFIED),
    ("other", evidence.UNKNOWN_ACQUISITION_UNVERIFIED),
    (None, evidence.UNKNOWN_ACQUISITION_UNVERIFIED),
])
def test_internal_acquisition_is_never_latest_verified(monkeypatch, method, status):
    reads = _mock_upload(monkeypatch, {
        "upload_origin": "internal_pipeline",
        "source_key": "gasca",
        "bridge_source": method,
        "provider_latest_verified": True,  # untrusted metadata claim
        "provider_revision": "fake-newest",
        "provider_published_at": "2099-01-01",
    })
    result = evidence.classify_kpi_desempeno_warehouse_evidence(
        warehouse_upload_id=42, business_date=DAY,
    )
    assert result.status == status
    assert not result.provider_latest_verified
    assert not result.execution_allowed
    assert reads["uploads"] == reads["audits"] == 1
    assert reads["filter"] == [{
        "upload_id": 42, "action": "UPLOAD", "performed_by_user_id": 900,
    }]


@pytest.mark.parametrize("details", [
    None,
    {},
    {"upload_origin": "manual", "source_key": "gasca"},
    {"upload_origin": "internal_pipeline", "source_key": "manual"},
    {"upload_origin": "internal_pipeline"},
])
def test_untrusted_upload_origin_fails_closed(monkeypatch, details):
    _mock_upload(monkeypatch, details)
    with pytest.raises(evidence.M3CSourceEvidenceError, match="internal Gasca"):
        evidence.classify_kpi_desempeno_warehouse_evidence(
            warehouse_upload_id=42, business_date=DAY,
        )


@pytest.mark.parametrize("settings", [
    {"source_status": "ARCHIVED"},
    {"report_key": "venta_total"},
    {"period_type": "rango"},
    {"cutoff": DAY + timedelta(days=1)},
    {"file_deleted": True},
])
def test_only_active_kpi_daily_uploads_are_inspected(monkeypatch, settings):
    calls = _mock_upload(monkeypatch, {"upload_origin": "internal_pipeline", "source_key": "gasca"}, **settings)
    with pytest.raises(evidence.M3CSourceEvidenceError, match="active KPI"):
        evidence.classify_kpi_desempeno_warehouse_evidence(
            warehouse_upload_id=42, business_date=DAY,
        )
    assert calls["audits"] == 0


def test_no_original_upload_audit_fails_closed(monkeypatch):
    _mock_upload(monkeypatch, {}, audit_present=False)
    with pytest.raises(evidence.M3CSourceEvidenceError, match="UPLOAD audit"):
        evidence.classify_kpi_desempeno_warehouse_evidence(
            warehouse_upload_id=42, business_date=DAY,
        )


@pytest.mark.parametrize("id_value, date_value", [
    (True, DAY), (0, DAY), ("42", DAY), (42, "2026-10-20"), (42, None),
])
def test_invalid_input_rejected_before_queries(monkeypatch, id_value, date_value):
    reads = _mock_upload(monkeypatch, {})
    with pytest.raises(evidence.M3CSourceEvidenceError, match="positive upload"):
        evidence.classify_kpi_desempeno_warehouse_evidence(
            warehouse_upload_id=id_value, business_date=date_value,
        )
    assert reads["uploads"] == reads["audits"] == 0
