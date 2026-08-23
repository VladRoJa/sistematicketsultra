from datetime import date, datetime, timezone

import pytest
from flask import Flask
from sqlalchemy import text

from app.extensions import db
from app.models.warehouse import TrackDailyVersionORM
from app.warehouse.services.track_daily_query_version_service import (
    resolve_effective_track_daily_version,
    resolve_preferred_track_daily_version,
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
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )
        db.session.execute(
            text(
                """
                CREATE TABLE track_daily_mart (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    track_daily_version_id INTEGER NULL
                )
                """
            )
        )
        db.session.commit()

        yield app

        db.session.remove()


def _add_version(
    *,
    track_date: date,
    version_type: str,
    is_current: bool = True,
    status: str = "success",
) -> TrackDailyVersionORM:
    now = datetime.now(timezone.utc)
    version = TrackDailyVersionORM(
        track_date=track_date,
        version_type=version_type,
        status=status,
        is_current=is_current,
        trigger_source="test",
        retry_count=0,
        created_at=now,
        updated_at=now,
    )
    db.session.add(version)
    db.session.flush()
    return version


def _add_mart_row(version_id: int) -> None:
    db.session.execute(
        text(
            "INSERT INTO track_daily_mart (track_daily_version_id) "
            "VALUES (:version_id)"
        ),
        {"version_id": version_id},
    )
    db.session.commit()


def test_historical_canonical_close_wins_with_multiple_versions(isolated_app):
    target_date = date(2026, 4, 30)

    with isolated_app.app_context():
        old_base = _add_version(
            track_date=target_date,
            version_type="base_nocturna_canonica",
            is_current=False,
        )
        current_base = _add_version(
            track_date=target_date,
            version_type="base_nocturna_canonica",
        )
        current_close = _add_version(
            track_date=target_date,
            version_type="cierre_canonico",
        )
        _add_mart_row(old_base.id)
        _add_mart_row(current_base.id)
        _add_mart_row(current_close.id)

        resolved = resolve_effective_track_daily_version(
            track_date=target_date,
            generation_mode="official_closed_day",
            today=date(2026, 5, 1),
        )

        assert resolved is not None
        assert resolved.id == current_close.id


def test_historical_falls_back_to_current_nightly_base(isolated_app):
    target_date = date(2026, 5, 2)

    with isolated_app.app_context():
        current_base = _add_version(
            track_date=target_date,
            version_type="base_nocturna_canonica",
        )
        _add_mart_row(current_base.id)

        resolved = resolve_effective_track_daily_version(
            track_date=target_date,
            generation_mode="manual_preview",
            today=date(2026, 5, 3),
        )

        assert resolved is not None
        assert resolved.id == current_base.id


def test_current_manual_preview_uses_operational_preview(isolated_app):
    target_date = date(2026, 8, 17)

    with isolated_app.app_context():
        preview = _add_version(
            track_date=target_date,
            version_type="preview_operativo",
        )
        close = _add_version(
            track_date=target_date,
            version_type="cierre_canonico",
        )
        _add_mart_row(preview.id)
        _add_mart_row(close.id)

        resolved = resolve_effective_track_daily_version(
            track_date=target_date,
            generation_mode="manual_preview",
            today=target_date,
        )

        assert resolved is not None
        assert resolved.id == preview.id


def test_returns_none_when_no_effective_version_has_mart_rows(isolated_app):
    target_date = date(2026, 8, 16)

    with isolated_app.app_context():
        _add_version(
            track_date=target_date,
            version_type="cierre_canonico",
        )
        db.session.commit()

        resolved = resolve_effective_track_daily_version(
            track_date=target_date,
            generation_mode="official_closed_day",
            today=date(2026, 8, 17),
        )

        assert resolved is None


def test_preferred_version_canonical_wins_over_preview(isolated_app):
    target_date = date(2026, 8, 23)

    with isolated_app.app_context():
        preview = _add_version(
            track_date=target_date,
            version_type="preview_operativo",
        )
        canonical = _add_version(
            track_date=target_date,
            version_type="cierre_canonico",
        )
        _add_mart_row(preview.id)
        _add_mart_row(canonical.id)

        resolved = resolve_preferred_track_daily_version(
            track_date=target_date,
        )

        assert resolved is not None
        assert resolved.id == canonical.id
        assert resolved.version_type == "cierre_canonico"


def test_preferred_version_nightly_base_wins_over_preview(isolated_app):
    target_date = date(2026, 8, 23)

    with isolated_app.app_context():
        preview = _add_version(
            track_date=target_date,
            version_type="preview_operativo",
        )
        nightly_base = _add_version(
            track_date=target_date,
            version_type="base_nocturna_canonica",
        )
        _add_mart_row(preview.id)
        _add_mart_row(nightly_base.id)

        resolved = resolve_preferred_track_daily_version(
            track_date=target_date,
        )

        assert resolved is not None
        assert resolved.id == nightly_base.id
        assert resolved.version_type == "base_nocturna_canonica"


def test_preferred_version_falls_back_to_preview(isolated_app):
    target_date = date(2026, 8, 23)

    with isolated_app.app_context():
        preview = _add_version(
            track_date=target_date,
            version_type="preview_operativo",
        )
        _add_mart_row(preview.id)

        resolved = resolve_preferred_track_daily_version(
            track_date=target_date,
        )

        assert resolved is not None
        assert resolved.id == preview.id
        assert resolved.version_type == "preview_operativo"


def test_preferred_version_returns_none_without_queryable_versions(
    isolated_app,
):
    target_date = date(2026, 8, 23)

    with isolated_app.app_context():
        _add_version(
            track_date=target_date,
            version_type="cierre_canonico",
        )
        _add_version(
            track_date=target_date,
            version_type="preview_operativo",
        )
        db.session.commit()

        resolved = resolve_preferred_track_daily_version(
            track_date=target_date,
        )

        assert resolved is None


def test_rejects_unknown_generation_mode(isolated_app):
    with isolated_app.app_context(), pytest.raises(
        ValueError,
        match="generation_mode inválido",
    ):
        resolve_effective_track_daily_version(
            track_date=date(2026, 8, 17),
            generation_mode="unknown",
            today=date(2026, 8, 17),
        )
