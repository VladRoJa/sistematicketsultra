from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.warehouse.scheduler import (
    reports_scheduler_worker as worker,
)


TIJUANA = ZoneInfo("America/Tijuana")


@pytest.fixture(autouse=True)
def reset_scheduler_state():
    worker._COMPLETED_BY_JOB_AND_DATE.clear()
    worker._NEXT_RETRY_BY_JOB_AND_DATE.clear()

    yield

    worker._COMPLETED_BY_JOB_AND_DATE.clear()
    worker._NEXT_RETRY_BY_JOB_AND_DATE.clear()


def test_cobranza_waits_when_track_priority_blocks(
    monkeypatch,
):
    calls = {"job": 0}

    monkeypatch.setattr(
        worker,
        "_should_run_daily_job",
        lambda **kwargs: True,
    )
    monkeypatch.setattr(
        worker,
        "get_secondary_job_block_reason",
        lambda now: "track_reserved_window",
    )

    def fake_job(*, business_date):
        calls["job"] += 1
        raise AssertionError(
            "Cobranza no debía ejecutarse."
        )

    monkeypatch.setattr(
        worker,
        "run_cobranza_recurrente_job",
        fake_job,
    )

    now = datetime(
        2026,
        8,
        24,
        9,
        10,
        tzinfo=TIJUANA,
    )

    worker._run_cobranza_recurrente_if_due(
        now
    )

    assert calls["job"] == 0
    assert not worker._COMPLETED_BY_JOB_AND_DATE


def test_cobranza_runs_when_track_priority_allows(
    monkeypatch,
):
    calls = {"job": 0}

    monkeypatch.setattr(
        worker,
        "_should_run_daily_job",
        lambda **kwargs: True,
    )
    monkeypatch.setattr(
        worker,
        "get_secondary_job_block_reason",
        lambda now: None,
    )

    monkeypatch.setattr(
        worker,
        "_find_persisted_scheduler_job_completion",
        lambda **kwargs: None,
    )

    monkeypatch.setattr(
        worker,
        "_persist_scheduler_job_completion",
        lambda **kwargs: 123,
    )

    def fake_job(*, business_date):
        calls["job"] += 1

        return {
            "total_rows": 176,
            "total_files": 24,
            "duration_seconds": 48.4,
            "warehouse_publication": {
                "total_uploads": 25,
                "total_internal_documents": 24,
            },
        }

    monkeypatch.setattr(
        worker,
        "run_cobranza_recurrente_job",
        fake_job,
    )

    now = datetime(
        2026,
        8,
        24,
        8,
        40,
        tzinfo=TIJUANA,
    )

    worker._run_cobranza_recurrente_if_due(
        now
    )

    assert calls["job"] == 1

    assert (
        "cobranza_recurrente_rechazados",
        now.date(),
    ) in worker._COMPLETED_BY_JOB_AND_DATE

def test_reporte_direccion_capture_disabled_by_default(
    monkeypatch,
):
    calls = {"job": 0}

    monkeypatch.delenv(
        "REPORTE_DIRECCION_DAILY_CAPTURE_ENABLED",
        raising=False,
    )

    def fake_job(*, business_date):
        calls["job"] += 1
        raise AssertionError(
            "Reporte Dirección no debía ejecutarse."
        )

    monkeypatch.setattr(
        worker,
        "run_reporte_direccion_daily_capture_job",
        fake_job,
    )

    now = datetime(
        2026,
        9,
        5,
        23,
        20,
        tzinfo=TIJUANA,
    )

    worker._run_reporte_direccion_daily_capture_if_due(
        now
    )

    assert calls["job"] == 0


def test_reporte_direccion_capture_waits_when_track_active(
    monkeypatch,
):
    calls = {"job": 0}

    monkeypatch.setenv(
        "REPORTE_DIRECCION_DAILY_CAPTURE_ENABLED",
        "true",
    )

    monkeypatch.setattr(
        worker,
        "_find_existing_nightly_reporte_direccion_snapshot",
        lambda **kwargs: None,
    )

    monkeypatch.setattr(
        worker,
        "get_nightly_report_capture_block_reason",
        lambda now: "track_active",
    )

    def fake_job(*, business_date):
        calls["job"] += 1
        raise AssertionError(
            "Reporte Dirección no debía ejecutarse."
        )

    monkeypatch.setattr(
        worker,
        "run_reporte_direccion_daily_capture_job",
        fake_job,
    )

    now = datetime(
        2026,
        9,
        5,
        23,
        20,
        tzinfo=TIJUANA,
    )

    worker._run_reporte_direccion_daily_capture_if_due(
        now
    )

    assert calls["job"] == 0
    assert not worker._COMPLETED_BY_JOB_AND_DATE


def test_reporte_direccion_capture_runs_when_allowed(
    monkeypatch,
):
    calls = []

    monkeypatch.setenv(
        "REPORTE_DIRECCION_DAILY_CAPTURE_ENABLED",
        "true",
    )

    monkeypatch.setattr(
        worker,
        "_find_existing_nightly_reporte_direccion_snapshot",
        lambda **kwargs: None,
    )

    monkeypatch.setattr(
        worker,
        "get_nightly_report_capture_block_reason",
        lambda now: None,
    )

    def fake_job(*, business_date):
        calls.append(business_date)

        return {
            "status": "completed",
            "business_date": business_date.isoformat(),
            "warehouse_upload_id": 12345,
            "snapshot_id": 67890,
            "ingestion_status": "ingested",
        }

    monkeypatch.setattr(
        worker,
        "run_reporte_direccion_daily_capture_job",
        fake_job,
    )

    now = datetime(
        2026,
        9,
        5,
        23,
        20,
        tzinfo=TIJUANA,
    )

    worker._run_reporte_direccion_daily_capture_if_due(
        now
    )

    assert calls == [
        now.date(),
    ]

    assert (
        "reporte_direccion_daily_capture",
        now.date(),
    ) in worker._COMPLETED_BY_JOB_AND_DATE

def test_reporte_direccion_capture_reuses_persisted_nightly_snapshot(
    monkeypatch,
):
    class ExistingSnapshot:
        id = 2468
        warehouse_upload_id = 1357

    calls = {"job": 0}

    monkeypatch.setenv(
        "REPORTE_DIRECCION_DAILY_CAPTURE_ENABLED",
        "true",
    )

    monkeypatch.setattr(
        worker,
        "_find_existing_nightly_reporte_direccion_snapshot",
        lambda **kwargs: ExistingSnapshot(),
    )

    def fake_job(*, business_date):
        calls["job"] += 1
        raise AssertionError(
            "No debía descargar nuevamente Reporte Dirección."
        )

    monkeypatch.setattr(
        worker,
        "run_reporte_direccion_daily_capture_job",
        fake_job,
    )

    now = datetime(
        2026,
        9,
        5,
        23,
        22,
        tzinfo=TIJUANA,
    )

    worker._run_reporte_direccion_daily_capture_if_due(
        now
    )

    assert calls["job"] == 0

    assert (
        "reporte_direccion_daily_capture",
        now.date(),
    ) in worker._COMPLETED_BY_JOB_AND_DATE

def test_find_existing_nightly_snapshot_ignores_daytime_capture(
    monkeypatch,
):
    class Snapshot:
        id = 100
        warehouse_upload_id = 200
        captured_at = datetime(
            2026,
            9,
            5,
            19,
            0,
            tzinfo=TIJUANA,
        )

    class FakeQuery:
        def filter_by(self, **kwargs):
            assert kwargs == {
                "business_date": datetime(
                    2026,
                    9,
                    5,
                    tzinfo=TIJUANA,
                ).date(),
                "snapshot_kind": "daily",
            }
            return self

        def order_by(self, *args):
            return self

        def all(self):
            return [Snapshot()]

    class FakeId:
        @staticmethod
        def desc():
            return "id_desc"

    class FakeModel:
        id = FakeId()
        query = FakeQuery()

    monkeypatch.setattr(
        worker,
        "ReporteDireccionSnapshotORM",
        FakeModel,
    )

    now = datetime(
        2026,
        9,
        5,
        23,
        22,
        tzinfo=TIJUANA,
    )

    result = (
        worker._find_existing_nightly_reporte_direccion_snapshot(
            business_date=now.date(),
            now=now,
        )
    )

    assert result is None


def test_find_existing_nightly_snapshot_accepts_nightly_capture(
    monkeypatch,
):
    class Snapshot:
        id = 101
        warehouse_upload_id = 201
        captured_at = datetime(
            2026,
            9,
            5,
            23,
            22,
            tzinfo=TIJUANA,
        )

    class FakeQuery:
        def filter_by(self, **kwargs):
            assert kwargs == {
                "business_date": datetime(
                    2026,
                    9,
                    5,
                    tzinfo=TIJUANA,
                ).date(),
                "snapshot_kind": "daily",
            }
            return self

        def order_by(self, *args):
            return self

        def all(self):
            return [Snapshot()]

    class FakeId:
        @staticmethod
        def desc():
            return "id_desc"

    class FakeModel:
        id = FakeId()
        query = FakeQuery()

    monkeypatch.setattr(
        worker,
        "ReporteDireccionSnapshotORM",
        FakeModel,
    )

    now = datetime(
        2026,
        9,
        5,
        23,
        22,
        tzinfo=TIJUANA,
    )

    result = (
        worker._find_existing_nightly_reporte_direccion_snapshot(
            business_date=now.date(),
            now=now,
        )
    )

    assert result is not None
    assert result.id == 101
    assert result.warehouse_upload_id == 201

def test_cobranza_persists_completion_after_success(
    monkeypatch,
):
    persisted = []

    monkeypatch.setattr(
        worker,
        "_should_run_daily_job",
        lambda **kwargs: True,
    )

    monkeypatch.setattr(
        worker,
        "get_secondary_job_block_reason",
        lambda now: None,
    )

    monkeypatch.setattr(
        worker,
        "_find_persisted_scheduler_job_completion",
        lambda **kwargs: None,
    )

    monkeypatch.setattr(
        worker,
        "run_cobranza_recurrente_job",
        lambda *, business_date: {
            "total_rows": 100,
            "total_files": 25,
            "duration_seconds": 40.0,
            "warehouse_publication": {
                "total_uploads": 26,
                "total_internal_documents": 25,
            },
        },
    )

    def fake_persist(*, job_key, business_date):
        persisted.append(
            (job_key, business_date)
        )
        return 999

    monkeypatch.setattr(
        worker,
        "_persist_scheduler_job_completion",
        fake_persist,
    )

    now = datetime(
        2026,
        9,
        5,
        8,
        40,
        tzinfo=TIJUANA,
    )

    worker._run_cobranza_recurrente_if_due(now)

    assert persisted == [
        (
            "cobranza_recurrente_rechazados",
            now.date(),
        )
    ]

    assert (
        "cobranza_recurrente_rechazados",
        now.date(),
    ) in worker._COMPLETED_BY_JOB_AND_DATE

def test_cobranza_skips_when_persisted_completion_exists(
    monkeypatch,
):
    calls = {"job": 0}

    monkeypatch.setattr(
        worker,
        "_should_run_daily_job",
        lambda **kwargs: True,
    )

    monkeypatch.setattr(
        worker,
        "get_secondary_job_block_reason",
        lambda now: None,
    )

    class ExistingCompletion:
        id = 321

    monkeypatch.setattr(
        worker,
        "_find_persisted_scheduler_job_completion",
        lambda **kwargs: ExistingCompletion(),
    )

    def fake_job(*, business_date):
        calls["job"] += 1
        raise AssertionError(
            "Cobranza no debía volver a entrar a GASCA."
        )

    monkeypatch.setattr(
        worker,
        "run_cobranza_recurrente_job",
        fake_job,
    )

    now = datetime(
        2026,
        9,
        5,
        20,
        23,
        tzinfo=TIJUANA,
    )

    worker._run_cobranza_recurrente_if_due(
        now
    )

    assert calls["job"] == 0

    assert (
        "cobranza_recurrente_rechazados",
        now.date(),
    ) in worker._COMPLETED_BY_JOB_AND_DATE

def test_find_persisted_scheduler_job_completion_filters_correctly(
    monkeypatch,
):
    class FakeAudit:
        def __init__(
            self,
            *,
            audit_id,
            details,
        ):
            self.id = audit_id
            self.details = details

    audits = [
        FakeAudit(
            audit_id=401,
            details={
                "source": "reports_scheduler",
                "job_key": "otro_job",
                "business_date": "2026-09-05",
                "status": "completed",
            },
        ),
        FakeAudit(
            audit_id=402,
            details={
                "source": "reports_scheduler",
                "job_key": "cobranza_recurrente_rechazados",
                "business_date": "2026-09-04",
                "status": "completed",
            },
        ),
        FakeAudit(
            audit_id=403,
            details={
                "source": "reports_scheduler",
                "job_key": "cobranza_recurrente_rechazados",
                "business_date": "2026-09-05",
                "status": "failed",
            },
        ),
        FakeAudit(
            audit_id=404,
            details={
                "source": "reports_scheduler",
                "job_key": "cobranza_recurrente_rechazados",
                "business_date": "2026-09-05",
                "status": "completed",
            },
        ),
    ]

    class FakeQuery:
        def filter_by(self, **kwargs):
            assert kwargs == {
                "action": "JOB_COMPLETED",
            }
            return self

        def order_by(self, *args):
            return self

        def all(self):
            return audits

    class FakeColumn:
        def desc(self):
            return self

    class FakeAuditModel:
        id = FakeColumn()
        query = FakeQuery()

    monkeypatch.setattr(
        worker,
        "WarehouseAuditLogORM",
        FakeAuditModel,
    )

    result = (
        worker._find_persisted_scheduler_job_completion(
            job_key="cobranza_recurrente_rechazados",
            business_date=datetime(
                2026,
                9,
                5,
                tzinfo=TIJUANA,
            ).date(),
        )
    )

    assert result is not None
    assert result.id == 404

def test_cobranza_not_ready_does_not_persist_completion(
    monkeypatch,
):
    persisted = []

    monkeypatch.setattr(
        worker,
        "_should_run_daily_job",
        lambda **kwargs: True,
    )

    monkeypatch.setattr(
        worker,
        "get_secondary_job_block_reason",
        lambda now: None,
    )

    monkeypatch.setattr(
        worker,
        "_find_persisted_scheduler_job_completion",
        lambda **kwargs: None,
    )

    def fake_job(*, business_date):
        raise worker.CobranzaRecurrenteNotReadyError(
            "Reporte todavía no disponible."
        )

    monkeypatch.setattr(
        worker,
        "run_cobranza_recurrente_job",
        fake_job,
    )

    def fake_persist(*, job_key, business_date):
        persisted.append(
            (job_key, business_date)
        )
        return 999

    monkeypatch.setattr(
        worker,
        "_persist_scheduler_job_completion",
        fake_persist,
    )

    now = datetime(
        2026,
        9,
        5,
        8,
        40,
        tzinfo=TIJUANA,
    )

    worker._run_cobranza_recurrente_if_due(now)

    assert persisted == []

    assert (
        "cobranza_recurrente_rechazados",
        now.date(),
    ) not in worker._COMPLETED_BY_JOB_AND_DATE

    assert (
        "cobranza_recurrente_rechazados",
        now.date(),
    ) in worker._NEXT_RETRY_BY_JOB_AND_DATE

def test_cobranza_technical_error_does_not_persist_completion(
    monkeypatch,
):
    persisted = []

    monkeypatch.setattr(
        worker,
        "_should_run_daily_job",
        lambda **kwargs: True,
    )

    monkeypatch.setattr(
        worker,
        "get_secondary_job_block_reason",
        lambda now: None,
    )

    monkeypatch.setattr(
        worker,
        "_find_persisted_scheduler_job_completion",
        lambda **kwargs: None,
    )

    def fake_job(*, business_date):
        raise RuntimeError(
            "Fallo técnico simulado."
        )

    monkeypatch.setattr(
        worker,
        "run_cobranza_recurrente_job",
        fake_job,
    )

    def fake_persist(*, job_key, business_date):
        persisted.append(
            (job_key, business_date)
        )
        return 999

    monkeypatch.setattr(
        worker,
        "_persist_scheduler_job_completion",
        fake_persist,
    )

    now = datetime(
        2026,
        9,
        5,
        8,
        40,
        tzinfo=TIJUANA,
    )

    worker._run_cobranza_recurrente_if_due(now)

    assert persisted == []

    assert (
        "cobranza_recurrente_rechazados",
        now.date(),
    ) not in worker._COMPLETED_BY_JOB_AND_DATE

    assert (
        "cobranza_recurrente_rechazados",
        now.date(),
    ) in worker._NEXT_RETRY_BY_JOB_AND_DATE
