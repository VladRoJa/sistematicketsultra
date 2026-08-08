from datetime import date
from types import SimpleNamespace

import pytest

import app.warehouse.services.track_daily_pipeline_service as service


TARGET_DATE = date(2026, 7, 31)
REQUEST_VERSION_ID = 55
BASE_VERSION_ID = 10
VENTA_TOTAL_SNAPSHOT_ID = 777
VENTA_TOTAL_UPLOAD_ID = 501


class _FakeSession:
    def __init__(self, events):
        self.events = events

    def commit(self):
        self.events.append("db_commit")

    def rollback(self):
        self.events.append("db_rollback")


def _install_common_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    events: list,
):
    request_version = SimpleNamespace(
        id=REQUEST_VERSION_ID,
        track_date=TARGET_DATE,
        version_type="cierre_canonico",
        status="pending",
        is_current=False,
        base_version_id=BASE_VERSION_ID,
        requested_by="admin_test",
        trigger_source="manual_canonical_close_request",
    )

    base_version = SimpleNamespace(
        id=BASE_VERSION_ID,
        track_date=TARGET_DATE,
        version_type="base_nocturna_canonica",
        status="success",
        is_current=True,
    )

    fake_session = _FakeSession(events)

    monkeypatch.setattr(
        service,
        "db",
        SimpleNamespace(session=fake_session),
    )

    def fake_get_version(version_id):
        assert version_id == REQUEST_VERSION_ID
        return request_version

    monkeypatch.setattr(
        service,
        "get_track_daily_version_by_id",
        fake_get_version,
    )

    def fake_mark_running(
        *,
        version_id,
        started_at_utc,
        auto_commit,
    ):
        assert version_id == REQUEST_VERSION_ID
        assert started_at_utc is not None
        assert auto_commit is True

        events.append("mark_running")
        request_version.status = "running"

        return request_version

    monkeypatch.setattr(
        service,
        "mark_track_daily_version_running",
        fake_mark_running,
    )

    def fake_get_current(
        *,
        track_date,
        version_type,
    ):
        assert track_date == TARGET_DATE
        assert version_type == "base_nocturna_canonica"
        return base_version

    monkeypatch.setattr(
        service,
        "get_current_track_daily_version",
        fake_get_current,
    )

    readiness_calls = []

    def fake_readiness(*, business_date):
        assert business_date == TARGET_DATE
        readiness_calls.append(business_date)
        events.append("readiness")
        return {
            "is_ready": True,
            "business_date": TARGET_DATE.isoformat(),
        }

    monkeypatch.setattr(
        service,
        "resolve_exact_agregadoras_snapshot_status_for_date",
        fake_readiness,
    )

    def fake_gasca_job(**kwargs):
        assert kwargs["report_type_key"] == "venta_total"
        assert kwargs["run_mode"] == "manual_retry"
        assert kwargs["snapshot_kind"] == "daily"
        assert kwargs["target_business_date"] == TARGET_DATE
        assert kwargs["force_ingestion"] is True
        assert kwargs["force_non_canonical"] is True

        events.append("venta_total_job")

        return {
            "job_status": "ingested",
            "report_type_key": "venta_total",
            "snapshot_id": VENTA_TOTAL_SNAPSHOT_ID,
            "warehouse_upload_id": VENTA_TOTAL_UPLOAD_ID,
            "force_non_canonical": True,
        }

    monkeypatch.setattr(
        service,
        "run_gasca_report_job",
        fake_gasca_job,
    )

    def fake_link_uploads(
        *,
        track_daily_version_id,
        warehouse_upload_ids,
        auto_commit,
    ):
        assert track_daily_version_id == REQUEST_VERSION_ID
        assert warehouse_upload_ids == [VENTA_TOTAL_UPLOAD_ID]
        assert auto_commit is False

        events.append("link_upload")

        return {
            "track_daily_version_id": REQUEST_VERSION_ID,
            "linked_count": 1,
        }

    monkeypatch.setattr(
        service,
        "link_warehouse_uploads_to_track_daily_version",
        fake_link_uploads,
    )

    def fake_refresh_agregadoras(
        *,
        business_date,
        generation_mode,
        agregadoras_policy,
    ):
        assert business_date == TARGET_DATE
        assert generation_mode == "official_closed_day"
        assert (
            agregadoras_policy
            == service.AGREGADORAS_POLICY_EXACT_REQUIRED
        )

        events.append("refresh_agregadoras")

        return {
            "agregadoras_business_date": TARGET_DATE.isoformat(),
            "rows_inserted": 25,
        }

    monkeypatch.setattr(
        service,
        "refresh_track_source_agregadoras_daily_for_track_date",
        fake_refresh_agregadoras,
    )

    def fake_refresh_ingresos(
        *,
        business_date,
        generation_mode,
        venta_total_snapshot_id,
    ):
        assert business_date == TARGET_DATE
        assert generation_mode == "official_closed_day"
        assert venta_total_snapshot_id == VENTA_TOTAL_SNAPSHOT_ID

        events.append("refresh_ingresos")

        return {
            "status": "refreshed",
            "source_snapshot_id": VENTA_TOTAL_SNAPSHOT_ID,
        }

    monkeypatch.setattr(
        service,
        "refresh_track_source_ingresos_daily_for_date",
        fake_refresh_ingresos,
    )

    def fake_refresh_tienda(*, business_date):
        assert business_date == TARGET_DATE
        events.append("refresh_tienda")

        return {
            "status": "refreshed",
        }

    monkeypatch.setattr(
        service,
        "refresh_track_source_tienda_daily_for_date",
        fake_refresh_tienda,
    )

    def fake_refresh_mart(
        *,
        business_date,
        generation_mode,
        track_daily_version_id,
    ):
        assert business_date == TARGET_DATE
        assert generation_mode == "official_closed_day"
        assert track_daily_version_id == REQUEST_VERSION_ID

        events.append("refresh_mart")

        return {
            "status": "refreshed",
            "rows_inserted": 25,
        }

    monkeypatch.setattr(
        service,
        "refresh_track_daily_mart_for_date",
        fake_refresh_mart,
    )

    return request_version, readiness_calls


def test_requested_canonical_close_promotes_only_after_mart(
    monkeypatch: pytest.MonkeyPatch,
):
    events = []

    _request_version, readiness_calls = (
        _install_common_dependencies(
            monkeypatch,
            events,
        )
    )

    def fake_promote_venta_total(
        *,
        snapshot_id,
        expected_business_date,
        expected_snapshot_kind,
        auto_commit,
    ):
        assert snapshot_id == VENTA_TOTAL_SNAPSHOT_ID
        assert expected_business_date == TARGET_DATE
        assert expected_snapshot_kind == "daily"
        assert auto_commit is False

        events.append("promote_venta_total")

        return {
            "status": "promoted",
            "snapshot_id": VENTA_TOTAL_SNAPSHOT_ID,
        }

    monkeypatch.setattr(
        service,
        "promote_venta_total_snapshot_canonical",
        fake_promote_venta_total,
    )

    promoted_version = SimpleNamespace(
        id=REQUEST_VERSION_ID,
        status="success",
        is_current=True,
        base_version_id=BASE_VERSION_ID,
    )

    def fake_promote_track(
        *,
        version_id,
        generated_at_utc,
        finished_at_utc,
        auto_commit,
    ):
        assert version_id == REQUEST_VERSION_ID
        assert generated_at_utc is not None
        assert finished_at_utc is not None
        assert auto_commit is False

        events.append("promote_track")

        return promoted_version

    monkeypatch.setattr(
        service,
        "promote_track_canonical_close",
        fake_promote_track,
    )

    result = service.run_requested_track_canonical_close(
        track_daily_version_id=REQUEST_VERSION_ID,
    )

    assert len(readiness_calls) == 2

    assert events == [
        "mark_running",
        "readiness",
        "venta_total_job",
        "link_upload",
        "readiness",
        "refresh_agregadoras",
        "refresh_ingresos",
        "refresh_tienda",
        "refresh_mart",
        "promote_venta_total",
        "promote_track",
        "db_commit",
    ]

    assert result["status"] == "completed"
    assert result["track_date"] == "2026-07-31"

    assert (
        result["venta_total_snapshot_id"]
        == VENTA_TOTAL_SNAPSHOT_ID
    )

    assert (
        result["venta_total_warehouse_upload_id"]
        == VENTA_TOTAL_UPLOAD_ID
    )

    assert result["track_daily_version"] == {
        "id": REQUEST_VERSION_ID,
        "version_type": "cierre_canonico",
        "status": "success",
        "is_current": True,
        "base_version_id": BASE_VERSION_ID,
    }


def test_requested_canonical_close_rolls_back_if_track_promotion_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    events = []

    _install_common_dependencies(
        monkeypatch,
        events,
    )

    def fake_promote_venta_total(**kwargs):
        assert kwargs["snapshot_id"] == VENTA_TOTAL_SNAPSHOT_ID
        assert kwargs["auto_commit"] is False

        events.append("promote_venta_total")

        return {
            "status": "promoted",
            "snapshot_id": VENTA_TOTAL_SNAPSHOT_ID,
        }

    monkeypatch.setattr(
        service,
        "promote_venta_total_snapshot_canonical",
        fake_promote_venta_total,
    )

    def fake_promote_track(**kwargs):
        assert kwargs["version_id"] == REQUEST_VERSION_ID
        assert kwargs["auto_commit"] is False

        events.append("promote_track_failed")

        raise RuntimeError("track promotion failed")

    monkeypatch.setattr(
        service,
        "promote_track_canonical_close",
        fake_promote_track,
    )

    def fake_mark_failed(
        *,
        version_id,
        error_message,
        finished_at_utc,
        auto_commit,
    ):
        assert version_id == REQUEST_VERSION_ID
        assert "track promotion failed" in error_message
        assert finished_at_utc is not None
        assert auto_commit is True

        events.append("mark_failed")

        return SimpleNamespace(
            id=version_id,
            status="failed",
            is_current=False,
        )

    monkeypatch.setattr(
        service,
        "mark_track_daily_version_failed",
        fake_mark_failed,
    )

    with pytest.raises(
        RuntimeError,
        match="track promotion failed",
    ):
        service.run_requested_track_canonical_close(
            track_daily_version_id=REQUEST_VERSION_ID,
        )

    assert "db_commit" not in events

    assert events[-4:] == [
        "promote_venta_total",
        "promote_track_failed",
        "db_rollback",
        "mark_failed",
    ]
