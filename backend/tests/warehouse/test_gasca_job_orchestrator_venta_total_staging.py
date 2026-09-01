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


def test_venta_total_retries_extraction_once_after_transient_failure(
    monkeypatch,
):
    app = _build_app()
    extraction_attempts = []

    def fake_extractor(**kwargs):
        extraction_attempts.append(dict(kwargs))

        if len(extraction_attempts) == 1:
            raise RuntimeError("Gasca transient loading timeout")

        return {
            "report_type_key": "venta_total",
            "original_filename": "venta_total_2026_08_31.xlsx",
            "content_type": (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            "file_bytes": b"fake-xlsx",
            "metadata": {
                "date_from": "2026-08-01",
                "date_to": "2026-08-31",
            },
        }

    def fake_upload_creator(**kwargs):
        return {
            "warehouse_upload_id": 901,
            "upload_status": "created",
        }

    def fake_venta_total_ingestor(**kwargs):
        return {
            "status": "ingested",
            "snapshot_id": 902,
        }

    app.config["WAREHOUSE_GASCA_EXTRACTOR"] = fake_extractor
    app.config["WAREHOUSE_INTERNAL_UPLOAD_CREATOR"] = (
        fake_upload_creator
    )
    app.config["WAREHOUSE_VENTA_TOTAL_INGESTOR"] = (
        fake_venta_total_ingestor
    )

    # El retry tiene una espera real en producción.
    # En pruebas la anulamos para no ralentizar pytest.
    monkeypatch.setattr(
        service,
        "sleep",
        lambda _seconds: None,
        raising=False,
    )

    with app.app_context():
        result = service.run_gasca_report_job(
            report_type_key="venta_total",
            run_mode="scheduled_daily",
            snapshot_kind="daily",
            requested_by="scheduler_test",
            trigger_source="track_scheduler",
            target_business_date=date(2026, 8, 31),
            force_ingestion=True,
        )

    assert len(extraction_attempts) == 2
    assert result["job_status"] == "ingested"
    assert result["snapshot_id"] == 902
    assert result["ingestion_status"] == "ingested"


def test_venta_total_stops_after_second_extraction_failure(
    monkeypatch,
):
    app = _build_app()
    extraction_attempts = []
    upload_calls = []
    ingestion_calls = []

    def fake_extractor(**kwargs):
        extraction_attempts.append(dict(kwargs))
        raise RuntimeError("Gasca loading timeout")

    def fake_upload_creator(**kwargs):
        upload_calls.append(dict(kwargs))
        raise AssertionError("No debe crear upload si falla extracción")

    def fake_venta_total_ingestor(**kwargs):
        ingestion_calls.append(dict(kwargs))
        raise AssertionError("No debe ingerir si falla extracción")

    app.config["WAREHOUSE_GASCA_EXTRACTOR"] = fake_extractor
    app.config["WAREHOUSE_INTERNAL_UPLOAD_CREATOR"] = (
        fake_upload_creator
    )
    app.config["WAREHOUSE_VENTA_TOTAL_INGESTOR"] = (
        fake_venta_total_ingestor
    )

    monkeypatch.setattr(
        service,
        "sleep",
        lambda _seconds: None,
    )

    with app.app_context():
        with pytest.raises(
            service.GascaProducerError,
            match="Falló la extracción desde Gasca",
        ):
            service.run_gasca_report_job(
                report_type_key="venta_total",
                run_mode="scheduled_daily",
                snapshot_kind="daily",
                requested_by="scheduler_test",
                trigger_source="track_scheduler",
                target_business_date=date(2026, 8, 31),
                force_ingestion=True,
            )

    assert len(extraction_attempts) == 2
    assert upload_calls == []
    assert ingestion_calls == []


def test_non_venta_total_does_not_retry_extraction(
    monkeypatch,
):
    app = _build_app()
    extraction_attempts = []

    def fake_extractor(**kwargs):
        extraction_attempts.append(dict(kwargs))
        raise RuntimeError("Gasca extraction failure")

    app.config["WAREHOUSE_GASCA_EXTRACTOR"] = fake_extractor

    monkeypatch.setattr(
        service,
        "sleep",
        lambda _seconds: None,
    )

    with app.app_context():
        with pytest.raises(
            service.GascaProducerError,
            match="Falló la extracción desde Gasca",
        ):
            service.run_gasca_report_job(
                report_type_key="reporte_direccion",
                run_mode="scheduled_daily",
                snapshot_kind="daily",
                requested_by="scheduler_test",
                trigger_source="track_scheduler",
                force_ingestion=True,
            )

    assert len(extraction_attempts) == 1

