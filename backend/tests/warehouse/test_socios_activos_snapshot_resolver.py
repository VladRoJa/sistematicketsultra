from datetime import date, datetime, timezone

import pytest
from flask import Flask
from sqlalchemy import text

from app.extensions import db
from app.models.warehouse import (
    SociosActivosSnapshotORM,
)
from app.warehouse.services import (
    socios_activos_snapshot_resolver as resolver,
)


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
                CREATE TABLE socios_activos_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    warehouse_upload_id INTEGER NOT NULL UNIQUE,
                    report_type_key VARCHAR(100) NOT NULL,
                    cutoff_date DATE NOT NULL,
                    captured_at DATETIME NOT NULL,
                    snapshot_kind VARCHAR(50) NOT NULL,
                    is_canonical BOOLEAN NOT NULL DEFAULT 0,
                    row_count_detected INTEGER NOT NULL,
                    row_count_valid INTEGER NOT NULL,
                    row_count_rejected INTEGER NOT NULL DEFAULT 0,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )
        db.session.commit()

        yield app

        db.session.remove()


def _create_snapshot(
    *,
    warehouse_upload_id,
    cutoff_date,
    captured_at,
    is_canonical,
    report_type_key="socios_activos",
    snapshot_kind="daily",
):
    now = datetime.now(timezone.utc)

    snapshot = SociosActivosSnapshotORM(
        warehouse_upload_id=warehouse_upload_id,
        report_type_key=report_type_key,
        cutoff_date=cutoff_date,
        captured_at=captured_at,
        snapshot_kind=snapshot_kind,
        is_canonical=is_canonical,
        row_count_detected=100,
        row_count_valid=100,
        row_count_rejected=0,
        created_at=now,
        updated_at=now,
    )

    db.session.add(snapshot)
    db.session.commit()

    return snapshot


def test_returns_latest_canonical_after_minimum_date(
    isolated_app,
):
    with isolated_app.app_context():
        older = _create_snapshot(
            warehouse_upload_id=1001,
            cutoff_date=date(2026, 8, 24),
            captured_at=datetime(
                2026,
                8,
                24,
                18,
                0,
                tzinfo=timezone.utc,
            ),
            is_canonical=True,
        )

        latest = _create_snapshot(
            warehouse_upload_id=1002,
            cutoff_date=date(2026, 8, 25),
            captured_at=datetime(
                2026,
                8,
                25,
                18,
                0,
                tzinfo=timezone.utc,
            ),
            is_canonical=True,
        )

        resolved = (
            resolver
            .resolve_latest_canonical_socios_activos_snapshot(
                minimum_cutoff_date="2026-08-23"
            )
        )

        assert resolved is not None
        assert resolved.id == latest.id
        assert resolved.id != older.id


def test_ignores_noncanonical_snapshot(
    isolated_app,
):
    with isolated_app.app_context():
        canonical = _create_snapshot(
            warehouse_upload_id=2001,
            cutoff_date=date(2026, 8, 25),
            captured_at=datetime(
                2026,
                8,
                25,
                17,
                0,
                tzinfo=timezone.utc,
            ),
            is_canonical=True,
        )

        _create_snapshot(
            warehouse_upload_id=2002,
            cutoff_date=date(2026, 8, 26),
            captured_at=datetime(
                2026,
                8,
                26,
                18,
                0,
                tzinfo=timezone.utc,
            ),
            is_canonical=False,
        )

        resolved = (
            resolver
            .resolve_latest_canonical_socios_activos_snapshot(
                minimum_cutoff_date=date(
                    2026,
                    8,
                    23,
                )
            )
        )

        assert resolved is not None
        assert resolved.id == canonical.id


def test_fails_closed_when_all_snapshots_are_too_old(
    isolated_app,
):
    with isolated_app.app_context():
        _create_snapshot(
            warehouse_upload_id=3001,
            cutoff_date=date(2026, 8, 22),
            captured_at=datetime(
                2026,
                8,
                22,
                18,
                0,
                tzinfo=timezone.utc,
            ),
            is_canonical=True,
        )

        resolved = (
            resolver
            .resolve_latest_canonical_socios_activos_snapshot(
                minimum_cutoff_date="2026-08-23"
            )
        )

        assert resolved is None


def test_same_cutoff_prefers_latest_captured_at(
    isolated_app,
):
    with isolated_app.app_context():
        older_capture = _create_snapshot(
            warehouse_upload_id=4001,
            cutoff_date=date(2026, 8, 25),
            captured_at=datetime(
                2026,
                8,
                25,
                17,
                0,
                tzinfo=timezone.utc,
            ),
            is_canonical=True,
        )

        newer_capture = _create_snapshot(
            warehouse_upload_id=4002,
            cutoff_date=date(2026, 8, 25),
            captured_at=datetime(
                2026,
                8,
                25,
                18,
                0,
                tzinfo=timezone.utc,
            ),
            is_canonical=True,
        )

        resolved = (
            resolver
            .resolve_latest_canonical_socios_activos_snapshot(
                minimum_cutoff_date="2026-08-25"
            )
        )

        assert resolved is not None
        assert resolved.id == newer_capture.id
        assert resolved.id != older_capture.id


def test_rejects_unsupported_snapshot_kind(
    isolated_app,
):
    with isolated_app.app_context():
        with pytest.raises(
            resolver.SociosActivosSnapshotResolverError,
            match="snapshot_kind no soportado",
        ):
            resolver.resolve_latest_canonical_socios_activos_snapshot(
                minimum_cutoff_date="2026-08-25",
                snapshot_kind="month_to_date",
            )
