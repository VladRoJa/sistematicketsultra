from datetime import date, datetime, timezone

import pytest
from flask import Flask
from sqlalchemy import text

from app.extensions import db
from app.models.warehouse import SociosActivosSnapshotORM
from app.warehouse.services import (
    socios_activos_repository as repository,
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
    row_count_valid,
):
    now = datetime.now(timezone.utc)

    snapshot = SociosActivosSnapshotORM(
        warehouse_upload_id=warehouse_upload_id,
        report_type_key="socios_activos",
        cutoff_date=cutoff_date,
        captured_at=captured_at,
        snapshot_kind="daily",
        is_canonical=is_canonical,
        row_count_detected=row_count_valid,
        row_count_valid=row_count_valid,
        row_count_rejected=0,
        created_at=now,
        updated_at=now,
    )

    db.session.add(snapshot)
    db.session.commit()

    return snapshot


def test_promotes_first_snapshot(
    isolated_app,
):
    target_date = date(2026, 8, 25)

    with isolated_app.app_context():
        snapshot = _create_snapshot(
            warehouse_upload_id=1001,
            cutoff_date=target_date,
            captured_at=datetime(
                2026,
                8,
                25,
                18,
                0,
                tzinfo=timezone.utc,
            ),
            is_canonical=False,
            row_count_valid=36274,
        )

        result = (
            repository
            .promote_socios_activos_snapshot_canonical(
                snapshot_id=snapshot.id,
                expected_cutoff_date=target_date,
                expected_snapshot_kind="daily",
                auto_commit=True,
            )
        )

        db.session.refresh(snapshot)

        assert result["status"] == "promoted"
        assert result["snapshot_id"] == snapshot.id
        assert result["cutoff_date"] == "2026-08-25"
        assert result["snapshot_kind"] == "daily"
        assert result["is_canonical"] is True
        assert result["replaced_snapshot_ids"] == []

        assert snapshot.is_canonical is True


def test_replaces_existing_canonical(
    isolated_app,
):
    target_date = date(2026, 8, 25)

    with isolated_app.app_context():
        previous_snapshot = _create_snapshot(
            warehouse_upload_id=2001,
            cutoff_date=target_date,
            captured_at=datetime(
                2026,
                8,
                25,
                17,
                0,
                tzinfo=timezone.utc,
            ),
            is_canonical=True,
            row_count_valid=40000,
        )

        corrected_snapshot = _create_snapshot(
            warehouse_upload_id=2002,
            cutoff_date=target_date,
            captured_at=datetime(
                2026,
                8,
                25,
                18,
                0,
                tzinfo=timezone.utc,
            ),
            is_canonical=False,
            row_count_valid=36274,
        )

        assert (
            corrected_snapshot.row_count_valid
            < previous_snapshot.row_count_valid
        )

        result = (
            repository
            .promote_socios_activos_snapshot_canonical(
                snapshot_id=corrected_snapshot.id,
                expected_cutoff_date=target_date,
                expected_snapshot_kind="daily",
                auto_commit=True,
            )
        )

        db.session.refresh(previous_snapshot)
        db.session.refresh(corrected_snapshot)

        assert result["status"] == "promoted"
        assert result["snapshot_id"] == corrected_snapshot.id
        assert result["replaced_snapshot_ids"] == [
            previous_snapshot.id
        ]

        assert previous_snapshot.is_canonical is False
        assert corrected_snapshot.is_canonical is True


def test_promoting_same_snapshot_is_idempotent(
    isolated_app,
):
    target_date = date(2026, 8, 25)

    with isolated_app.app_context():
        snapshot = _create_snapshot(
            warehouse_upload_id=3001,
            cutoff_date=target_date,
            captured_at=datetime(
                2026,
                8,
                25,
                18,
                0,
                tzinfo=timezone.utc,
            ),
            is_canonical=True,
            row_count_valid=36274,
        )

        result = (
            repository
            .promote_socios_activos_snapshot_canonical(
                snapshot_id=snapshot.id,
                expected_cutoff_date=target_date,
                expected_snapshot_kind="daily",
                auto_commit=True,
            )
        )

        db.session.refresh(snapshot)

        assert result["status"] == "promoted"
        assert result["snapshot_id"] == snapshot.id
        assert result["is_canonical"] is True
        assert result["replaced_snapshot_ids"] == []

        assert snapshot.is_canonical is True


def test_expected_cutoff_date_fails_closed(
    isolated_app,
):
    actual_date = date(2026, 8, 25)

    with isolated_app.app_context():
        snapshot = _create_snapshot(
            warehouse_upload_id=4001,
            cutoff_date=actual_date,
            captured_at=datetime(
                2026,
                8,
                25,
                18,
                0,
                tzinfo=timezone.utc,
            ),
            is_canonical=False,
            row_count_valid=36274,
        )

        with pytest.raises(
            repository.SociosActivosRepositoryError,
            match="cutoff_date inesperado",
        ):
            repository.promote_socios_activos_snapshot_canonical(
                snapshot_id=snapshot.id,
                expected_cutoff_date=date(
                    2026,
                    8,
                    24,
                ),
                expected_snapshot_kind="daily",
                auto_commit=True,
            )

        db.session.refresh(snapshot)

        assert snapshot.is_canonical is False
