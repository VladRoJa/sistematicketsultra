from datetime import date

import pytest

from app.warehouse.services.socios_activos_sync_service import (
    sync_socios_activos_daily,
)


def test_daily_sync_ingests_and_promotes_canonical():
    captured = {}

    def fake_job_runner(**kwargs):
        captured["job"] = dict(kwargs)
        return {
            "ingestion_status": "ingested",
            "snapshot_id": 801,
            "warehouse_upload_id": 901,
        }

    def fake_promoter(**kwargs):
        captured["promotion"] = dict(kwargs)
        return {
            "status": "promoted",
            "snapshot_id": 801,
            "is_canonical": True,
        }

    result = sync_socios_activos_daily(
        business_date=date(2026, 9, 7),
        requested_by="reports_scheduler",
        job_runner=fake_job_runner,
        canonical_promoter=fake_promoter,
    )

    assert captured["job"]["report_type_key"] == "socios_activos"
    assert captured["job"]["target_business_date"] == date(2026, 9, 7)
    assert captured["promotion"] == {
        "snapshot_id": 801,
        "expected_cutoff_date": date(2026, 9, 7),
        "expected_snapshot_kind": "daily",
        "auto_commit": True,
    }
    assert result["canonical_promotion"]["is_canonical"] is True


def test_daily_sync_does_not_promote_failed_ingestion():
    promoted = False

    def fake_job_runner(**kwargs):
        return {
            "ingestion_status": "not_applicable",
            "snapshot_id": None,
        }

    def fake_promoter(**kwargs):
        nonlocal promoted
        promoted = True
        return {}

    with pytest.raises(RuntimeError, match="no confirmó la ingesta"):
        sync_socios_activos_daily(
            business_date=date(2026, 9, 7),
            job_runner=fake_job_runner,
            canonical_promoter=fake_promoter,
        )

    assert promoted is False
