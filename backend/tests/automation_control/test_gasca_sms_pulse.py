"""Synthetic pulse telemetry: no browser, real phone or SMS."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.extensions import db
from app.models.automation_control import GascaSmsHealthPulseORM as Pulse
from app.routes.automation_control_routes import automation_control_bp
from app.services.automation_control.gasca_sms_pulse_service import (
    PULSE_INTERVAL_SECONDS, finish_pulse, pulse_slot_id, read_pulse_health,
    reserve_pulse,
)


@pytest.fixture
def app():
    instance = Flask(__name__)
    instance.config.update(
        TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        JWT_SECRET_KEY="pulse-tests",
    )
    db.init_app(instance)
    JWTManager(instance)
    instance.register_blueprint(automation_control_bp, url_prefix="/api/automation-control")
    with instance.app_context():
        Pulse.__table__.create(db.engine)
        yield instance
        db.session.remove()
        Pulse.__table__.drop(db.engine)


def test_slot_is_two_hours_and_requires_tz():
    epoch = datetime.fromtimestamp(20 * PULSE_INTERVAL_SECONDS, tz=timezone.utc)
    assert pulse_slot_id(epoch) == 20
    assert pulse_slot_id(epoch + timedelta(seconds=PULSE_INTERVAL_SECONDS - 1)) == 20
    assert pulse_slot_id(epoch + timedelta(seconds=PULSE_INTERVAL_SECONDS)) == 21
    with pytest.raises(ValueError, match="zona horaria"):
        pulse_slot_id(datetime(2026, 10, 20))


def test_unknown_success_failure_and_overdue_states(app):
    anchor = datetime(2026, 10, 20, 20, 0, tzinfo=timezone.utc)
    with app.app_context():
        assert read_pulse_health(anchor)["state"] == "UNKNOWN"
        previous = Pulse(
            slot_id=pulse_slot_id(anchor - timedelta(hours=2)),
            status="SENT", attempted_at=anchor - timedelta(hours=2),
            finished_at=anchor - timedelta(hours=2) + timedelta(seconds=4),
        )
        db.session.add(previous)
        db.session.commit()
        assert read_pulse_health(anchor)["state"] == "HEALTHY"
        assert read_pulse_health(anchor + timedelta(minutes=20))["state"] == "LATE"

        latest = Pulse(
            slot_id=pulse_slot_id(anchor), status="FAILED",
            attempted_at=anchor, finished_at=anchor + timedelta(seconds=3),
            error_code="SENDER_ERROR",
        )
        db.session.add(latest)
        db.session.commit()
        result = read_pulse_health(anchor + timedelta(minutes=1))
        assert result["state"] == "FAILED"
        assert result["last_error_code"] == "SENDER_ERROR"
        assert result["consecutive_failures"] == 1
        assert result["delivery_verified"] is False
        assert "phone" not in str(result).lower()
        assert "message" not in str(result).lower()


def test_started_pulse_is_not_success_and_stale_start_is_failure(app):
    now = datetime(2026, 10, 20, 20, 0, tzinfo=timezone.utc)
    with app.app_context():
        pulse = Pulse(slot_id=pulse_slot_id(now), status="STARTED", attempted_at=now)
        db.session.add(pulse)
        db.session.commit()
        assert read_pulse_health(now + timedelta(minutes=1))["state"] == "RUNNING"
        assert read_pulse_health(now + timedelta(minutes=11))["state"] == "FAILED"


def test_finish_pulse_rejects_arbitrary_error_text_and_is_terminal(app):
    now = datetime(2026, 10, 20, 20, 0, tzinfo=timezone.utc)
    with app.app_context():
        db.session.add(Pulse(slot_id=11, status="STARTED", attempted_at=now))
        db.session.commit()
        with pytest.raises(ValueError, match="Código"):
            finish_pulse(11, sent=False, error_code="RAW_PHONE_1234567890")
        finish_pulse(11, sent=False, error_code="SENDER_ERROR")
        with pytest.raises(RuntimeError, match="terminal"):
            finish_pulse(11, sent=True)
        db.session.rollback()
        assert db.session.get(Pulse, 11).status == "FAILED"


def test_claim_idempotent_on_insert_conflict_contract(app):
    with app.app_context():
        query = MagicMock()
        query.scalar_one_or_none.return_value = None
        with patch.object(db.session, "execute", return_value=query) as execute, patch.object(db.session, "commit") as commit:
            assert reserve_pulse(datetime(2026, 10, 20, 20, 0, tzinfo=timezone.utc)) is None
            execute.assert_called_once()
            assert "ON CONFLICT DO NOTHING" in str(execute.call_args.args[0].compile(
                dialect=__import__("sqlalchemy").dialects.postgresql.dialect()
            )).upper()
            commit.assert_called_once()


def test_pulse_endpoint_requires_jwt_and_admicorp(app):
    client = app.test_client()
    path = "/api/automation-control/sms-gasca/pulse"
    assert client.get(path).status_code == 401
    with app.app_context():
        token = create_access_token(identity="47")
    headers = {"Authorization": f"Bearer {token}"}
    with patch("app.routes.automation_control_routes._require_read_access", return_value=False):
        assert client.get(path, headers=headers).status_code == 403
    with patch("app.routes.automation_control_routes._require_read_access", return_value=True):
        response = client.get(path, headers=headers)
    assert response.status_code == 200
    assert response.get_json()["state"] == "UNKNOWN"
    assert client.post(path, headers=headers).status_code == 405
