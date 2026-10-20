"""Source audit tags must reflect trusted internal context, not extractor claims.

Synthetic unit-only tests: no browser, credentials, Warehouse writes or Gasca calls.
"""
from datetime import date, datetime, timezone

from flask import Flask

from app.warehouse.services import gasca_job_orchestrator as orchestrator
from app.warehouse.services import warehouse_upload_creator_existing_service as creator


def test_untrusted_gasca_artifact_cannot_override_run_context(monkeypatch):
    captured = {}

    def upload_creator(**kwargs):
        captured.update(kwargs)
        return {"warehouse_upload_id": 91, "upload_status": "created"}

    monkeypatch.setattr(orchestrator, "_get_required_callable", lambda *a, **k: upload_creator)
    command = orchestrator.GascaExtractionCommand(
        report_type_key="kpi_desempeno",
        run_mode="manual_retry",
        snapshot_kind="daily",
        requested_by="svc_track",
        trigger_source="track_batch",
        target_business_date=date(2026, 10, 20),
    )
    artifact = orchestrator.ProducedGascaArtifact(
        report_type_key="kpi_desempeno",
        original_filename="synthetic.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        captured_at=datetime(2026, 10, 20, tzinfo=timezone.utc),
        file_bytes=b"synthetic-no-real-gasca-content",
        metadata={
            "run_mode": "spoofed",
            "snapshot_kind": "spoofed",
            "requested_by": "spoofed",
            "trigger_source": "spoofed",
            "source_key": "manual",
            "upload_origin": "outside",
            "note": "free form retained",
        },
    )
    with Flask(__name__).app_context():
        result = orchestrator._create_warehouse_upload(command=command, artifact=artifact)

    assert result.warehouse_upload_id == 91
    assert captured["source_key"] == "gasca"
    assert captured["metadata"] == {
        "run_mode": "manual_retry",
        "snapshot_kind": "daily",
        "requested_by": "svc_track",
        "trigger_source": "track_batch",
        "source_key": "manual",
        "upload_origin": "outside",
        "note": "free form retained",
    }
    # The next trusted layer overrides source_key/upload_origin too.


def test_internal_upload_creator_overrides_reserved_origin_tags(monkeypatch):
    captured = {}

    def underlying(**kwargs):
        captured.update(kwargs)
        return {
            "warehouse_upload_id": 109,
            "report_type_key": "kpi_desempeno",
            "upload_status": "created",
        }

    monkeypatch.setattr(creator, "_resolve_internal_system_user_id", lambda: 7)
    monkeypatch.setattr(creator, "_resolve_period_for_internal_upload", lambda **kw: {
        "cutoff_date": date(2026, 10, 20),
        "date_from": None,
        "date_to": None,
    })
    monkeypatch.setattr(creator, "create_warehouse_document_upload", underlying)
    with Flask(__name__).app_context():
        result = creator.create_warehouse_upload_via_existing_service(
            report_type_key="kpi_desempeno",
            original_filename="synthetic.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            file_bytes=b"synthetic-not-a-production-file",
            captured_at=datetime(2026, 10, 20, tzinfo=timezone.utc),
            source_key="gasca",
            metadata={
                "upload_origin": "manual_override_attempt",
                "source_key": "unknown_override_attempt",
                "run_mode": "manual_retry",
                "snapshot_kind": "daily",
                "note": "kept",
            },
        )
    assert result["warehouse_upload_id"] == 109
    assert captured["uploaded_by_user_id"] == 7
    assert captured["audit_details"] == {
        "upload_origin": "internal_pipeline",
        "source_key": "gasca",
        "run_mode": "manual_retry",
        "snapshot_kind": "daily",
        "note": "kept",
    }


def test_internal_creator_default_origin_does_not_prove_gasca_latest(monkeypatch):
    captured = {}
    monkeypatch.setattr(creator, "_resolve_internal_system_user_id", lambda: 3)
    monkeypatch.setattr(creator, "_resolve_period_for_internal_upload", lambda **kw: {
        "cutoff_date": date(2026, 10, 20),
        "date_from": None,
        "date_to": None,
    })
    monkeypatch.setattr(
        creator, "create_warehouse_document_upload",
        lambda **kw: captured.update(kw) or {"warehouse_upload_id": 55},
    )
    with Flask(__name__).app_context():
        creator.create_warehouse_upload_via_existing_service(
            report_type_key="kpi_desempeno",
            original_filename="synthetic.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            file_bytes=b"fake",
            captured_at=datetime(2026, 10, 20, tzinfo=timezone.utc),
            metadata={"upload_origin": "forged"},
        )
    assert captured["audit_details"]["upload_origin"] == "internal_pipeline"
    assert captured["audit_details"]["source_key"] == "gasca"
    # No provider-issued report revision, assertion or external release time.
    assert "provider_revision" not in captured["audit_details"]
    assert "provider_published_at" not in captured["audit_details"]
