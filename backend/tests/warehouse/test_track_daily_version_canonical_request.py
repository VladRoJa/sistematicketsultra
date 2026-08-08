from datetime import date, timedelta

import pytest
from flask import Flask
from sqlalchemy import text

from app.extensions import db
from app.models.warehouse import TrackDailyVersionORM
from app.warehouse.services import track_daily_version_service as service


@pytest.fixture
def isolated_app():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite://",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    db.init_app(app)

    with app.app_context():
        db.session.execute(
            text(
                """
                CREATE TABLE track_daily_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    track_date DATE NOT NULL,
                    version_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    generated_at_utc DATETIME NULL,
                    started_at_utc DATETIME NULL,
                    finished_at_utc DATETIME NULL,
                    is_current BOOLEAN NOT NULL DEFAULT 1,
                    replaces_version_id INTEGER NULL,
                    base_version_id INTEGER NULL,
                    requested_by TEXT NULL,
                    trigger_source TEXT NOT NULL,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    FOREIGN KEY(replaces_version_id)
                        REFERENCES track_daily_versions(id),
                    FOREIGN KEY(base_version_id)
                        REFERENCES track_daily_versions(id)
                )
                """
            )
        )
        db.session.commit()

        yield app

        db.session.remove()


def _create_version(
    *,
    track_date,
    version_type,
    status,
    is_current,
    trigger_source,
):
    return service.create_track_daily_version(
        track_date=track_date,
        version_type=version_type,
        status=status,
        is_current=is_current,
        trigger_source=trigger_source,
        auto_commit=True,
    )


def test_request_canonical_close_is_pending_and_not_current(
    isolated_app,
):
    target_date = date(2026, 7, 31)

    with isolated_app.app_context():
        base = _create_version(
            track_date=target_date,
            version_type="base_nocturna_canonica",
            status="success",
            is_current=True,
            trigger_source="test_base",
        )

        previous_close = _create_version(
            track_date=target_date,
            version_type="cierre_canonico",
            status="success",
            is_current=True,
            trigger_source="test_previous_close",
        )

        request_version = service.request_track_canonical_close(
            track_date=target_date,
            requested_by="admin_test",
            trigger_source="manual_canonical_close_request",
            auto_commit=True,
        )

        assert request_version.version_type == "cierre_canonico"
        assert request_version.status == "pending"
        assert request_version.is_current is False

        assert request_version.base_version_id == base.id
        assert request_version.replaces_version_id == previous_close.id
        assert request_version.requested_by == "admin_test"
        assert request_version.trigger_source == (
            "manual_canonical_close_request"
        )

        db.session.refresh(previous_close)

        assert previous_close.status == "success"
        assert previous_close.is_current is True


def test_request_canonical_close_reuses_existing_pending_request(
    isolated_app,
):
    target_date = date(2026, 7, 31)

    with isolated_app.app_context():
        _create_version(
            track_date=target_date,
            version_type="base_nocturna_canonica",
            status="success",
            is_current=True,
            trigger_source="test_base",
        )

        first_request = service.request_track_canonical_close(
            track_date=target_date,
            requested_by="admin_test",
            auto_commit=True,
        )

        second_request = service.request_track_canonical_close(
            track_date=target_date,
            requested_by="admin_test",
            auto_commit=True,
        )

        assert second_request.id == first_request.id

        pending_count = (
            TrackDailyVersionORM.query.filter_by(
                track_date=target_date,
                version_type="cierre_canonico",
                status="pending",
                is_current=False,
            )
            .count()
        )

        assert pending_count == 1


def test_request_canonical_close_requires_successful_current_base(
    isolated_app,
):
    target_date = date(2026, 7, 31)

    with isolated_app.app_context():
        with pytest.raises(
            service.TrackDailyVersionServiceError,
            match="base_nocturna_canonica current y success",
        ):
            service.request_track_canonical_close(
                track_date=target_date,
                requested_by="admin_test",
                auto_commit=True,
            )


def test_promote_canonical_close_replaces_previous_only_at_end(
    isolated_app,
):
    target_date = date(2026, 7, 31)

    with isolated_app.app_context():
        base = _create_version(
            track_date=target_date,
            version_type="base_nocturna_canonica",
            status="success",
            is_current=True,
            trigger_source="test_base",
        )

        previous_close = _create_version(
            track_date=target_date,
            version_type="cierre_canonico",
            status="success",
            is_current=True,
            trigger_source="test_previous_close",
        )

        request_version = service.request_track_canonical_close(
            track_date=target_date,
            requested_by="admin_test",
            auto_commit=True,
        )

        assert request_version.is_current is False
        assert request_version.status == "pending"
        assert request_version.replaces_version_id == previous_close.id
        assert request_version.base_version_id == base.id

        service.mark_track_daily_version_running(
            version_id=request_version.id,
            auto_commit=True,
        )

        db.session.refresh(previous_close)
        db.session.refresh(request_version)

        # Mientras el trabajo está running, el cierre anterior
        # continúa siendo el visible.
        assert previous_close.is_current is True
        assert previous_close.status == "success"

        assert request_version.is_current is False
        assert request_version.status == "running"

        promoted = service.promote_track_canonical_close(
            version_id=request_version.id,
            auto_commit=True,
        )

        db.session.refresh(previous_close)
        db.session.refresh(request_version)

        assert promoted.id == request_version.id

        assert previous_close.is_current is False
        assert previous_close.status == "replaced"

        assert request_version.is_current is True
        assert request_version.status == "success"
        assert request_version.generated_at_utc is not None
        assert request_version.finished_at_utc is not None
        assert request_version.error_message is None


def test_promote_canonical_close_rejects_stale_request(
    isolated_app,
):
    target_date = date(2026, 7, 31)

    with isolated_app.app_context():
        _create_version(
            track_date=target_date,
            version_type="base_nocturna_canonica",
            status="success",
            is_current=True,
            trigger_source="test_base",
        )

        original_close = _create_version(
            track_date=target_date,
            version_type="cierre_canonico",
            status="success",
            is_current=True,
            trigger_source="test_original_close",
        )

        request_version = service.request_track_canonical_close(
            track_date=target_date,
            requested_by="admin_test",
            auto_commit=True,
        )

        assert request_version.replaces_version_id == original_close.id

        service.mark_track_daily_version_running(
            version_id=request_version.id,
            auto_commit=True,
        )

        # Simula que otro proceso terminó un cierre más nuevo
        # mientras esta solicitud todavía estaba procesándose.
        service.mark_track_daily_version_replaced(
            version_id=original_close.id,
            auto_commit=True,
        )

        newer_close = _create_version(
            track_date=target_date,
            version_type="cierre_canonico",
            status="success",
            is_current=True,
            trigger_source="test_newer_close",
        )

        with pytest.raises(
            service.TrackDailyVersionServiceError,
            match="quedó obsoleta",
        ):
            service.promote_track_canonical_close(
                version_id=request_version.id,
                auto_commit=True,
            )

        db.session.rollback()

        db.session.refresh(request_version)
        db.session.refresh(newer_close)

        assert request_version.is_current is False
        assert request_version.status == "running"

        assert newer_close.is_current is True
        assert newer_close.status == "success"


def test_claim_next_pending_canonical_close_claims_oldest_and_keeps_non_current(
    isolated_app,
):
    first_date = date(2026, 7, 30)
    second_date = date(2026, 7, 31)

    with isolated_app.app_context():
        _create_version(
            track_date=first_date,
            version_type="base_nocturna_canonica",
            status="success",
            is_current=True,
            trigger_source="test_base_first",
        )

        first_request = service.request_track_canonical_close(
            track_date=first_date,
            requested_by="admin_test",
            auto_commit=True,
        )

        _create_version(
            track_date=second_date,
            version_type="base_nocturna_canonica",
            status="success",
            is_current=True,
            trigger_source="test_base_second",
        )

        second_request = service.request_track_canonical_close(
            track_date=second_date,
            requested_by="admin_test",
            auto_commit=True,
        )

        assert first_request.status == "pending"
        assert second_request.status == "pending"

        claimed = service.claim_next_pending_track_canonical_close(
            auto_commit=True,
        )

        assert claimed is not None
        assert claimed.id == first_request.id
        assert claimed.status == "running"
        assert claimed.is_current is False
        assert claimed.started_at_utc is not None

        db.session.refresh(second_request)

        assert second_request.status == "pending"
        assert second_request.is_current is False

        claimed_second = (
            service.claim_next_pending_track_canonical_close(
                auto_commit=True,
            )
        )

        assert claimed_second is not None
        assert claimed_second.id == second_request.id
        assert claimed_second.status == "running"
        assert claimed_second.is_current is False


def test_claim_next_pending_canonical_close_returns_none_when_empty(
    isolated_app,
):
    with isolated_app.app_context():
        claimed = service.claim_next_pending_track_canonical_close(
            auto_commit=True,
        )

        assert claimed is None


def test_claim_does_not_recover_recent_running(
    isolated_app,
):
    target_date = date(2026, 7, 31)

    with isolated_app.app_context():
        _create_version(
            track_date=target_date,
            version_type="base_nocturna_canonica",
            status="success",
            is_current=True,
            trigger_source="test_recent_running_base",
        )

        request_version = service.request_track_canonical_close(
            track_date=target_date,
            requested_by="admin_test",
            auto_commit=True,
        )

        claimed = service.claim_next_pending_track_canonical_close(
            lease_timeout_seconds=7200,
            max_recovery_retries=3,
            auto_commit=True,
        )

        assert claimed is not None
        assert claimed.id == request_version.id
        assert claimed.status == "running"
        assert claimed.is_current is False

        retry_count_before = int(
            claimed.retry_count or 0
        )

        claimed_again = (
            service.claim_next_pending_track_canonical_close(
                lease_timeout_seconds=7200,
                max_recovery_retries=3,
                auto_commit=True,
            )
        )

        assert claimed_again is None

        persisted = service.get_track_daily_version_by_id(
            request_version.id
        )

        assert persisted.status == "running"
        assert persisted.is_current is False
        assert int(persisted.retry_count or 0) == retry_count_before


def test_claim_recovers_stale_running_and_increments_retry(
    isolated_app,
):
    target_date = date(2026, 7, 30)

    with isolated_app.app_context():
        _create_version(
            track_date=target_date,
            version_type="base_nocturna_canonica",
            status="success",
            is_current=True,
            trigger_source="test_stale_running_base",
        )

        request_version = service.request_track_canonical_close(
            track_date=target_date,
            requested_by="admin_test",
            auto_commit=True,
        )

        claimed = service.claim_next_pending_track_canonical_close(
            lease_timeout_seconds=7200,
            max_recovery_retries=3,
            auto_commit=True,
        )

        assert claimed is not None
        assert claimed.status == "running"

        retry_count_before = int(
            claimed.retry_count or 0
        )

        claimed.updated_at = (
            service._now_utc() - timedelta(hours=3)
        )
        db.session.commit()

        recovered = service.claim_next_pending_track_canonical_close(
            lease_timeout_seconds=7200,
            max_recovery_retries=3,
            auto_commit=True,
        )

        assert recovered is not None
        assert recovered.id == request_version.id
        assert recovered.status == "running"
        assert recovered.is_current is False
        assert (
            int(recovered.retry_count or 0)
            == retry_count_before + 1
        )
        assert recovered.started_at_utc is not None
        assert recovered.finished_at_utc is None
        assert recovered.error_message is None


def test_claim_marks_stale_running_failed_after_retry_limit(
    isolated_app,
):
    target_date = date(2026, 7, 29)

    with isolated_app.app_context():
        _create_version(
            track_date=target_date,
            version_type="base_nocturna_canonica",
            status="success",
            is_current=True,
            trigger_source="test_exhausted_running_base",
        )

        request_version = service.request_track_canonical_close(
            track_date=target_date,
            requested_by="admin_test",
            auto_commit=True,
        )

        claimed = service.claim_next_pending_track_canonical_close(
            lease_timeout_seconds=7200,
            max_recovery_retries=3,
            auto_commit=True,
        )

        assert claimed is not None

        claimed.status = "running"
        claimed.retry_count = 3
        claimed.updated_at = (
            service._now_utc() - timedelta(hours=3)
        )
        db.session.commit()

        recovered = service.claim_next_pending_track_canonical_close(
            lease_timeout_seconds=7200,
            max_recovery_retries=3,
            auto_commit=True,
        )

        assert recovered is None

        persisted = service.get_track_daily_version_by_id(
            request_version.id
        )

        assert persisted.status == "failed"
        assert persisted.is_current is False
        assert int(persisted.retry_count or 0) == 3
        assert persisted.finished_at_utc is not None
        assert persisted.error_message is not None
        assert "lease vencido" in persisted.error_message
        assert (
            "límite de recuperaciones automáticas agotado"
            in persisted.error_message
        )


def test_get_latest_track_canonical_close_returns_latest_attempt(
    isolated_app,
):
    target_date = date(2026, 7, 31)

    with isolated_app.app_context():
        _create_version(
            track_date=target_date,
            version_type="base_nocturna_canonica",
            status="success",
            is_current=True,
            trigger_source="test_latest_base",
        )

        first_request = service.request_track_canonical_close(
            track_date=target_date,
            requested_by="admin_test",
            auto_commit=True,
        )

        first_request.status = "failed"
        first_request.error_message = "primer intento falló"
        db.session.commit()

        second_request = service.request_track_canonical_close(
            track_date=target_date,
            requested_by="admin_test",
            auto_commit=True,
        )

        latest = (
            service.get_latest_track_canonical_close_version(
                track_date=target_date,
            )
        )

        assert latest is not None
        assert latest.id == second_request.id
        assert latest.id != first_request.id
        assert latest.status == "pending"
        assert latest.is_current is False


def test_get_latest_track_canonical_close_returns_none_when_missing(
    isolated_app,
):
    with isolated_app.app_context():
        latest = (
            service.get_latest_track_canonical_close_version(
                track_date=date(2026, 7, 28),
            )
        )

        assert latest is None
