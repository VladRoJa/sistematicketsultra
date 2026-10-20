"""Worker control flow: no live SMS or Chrome; customer requests retain priority."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import Flask
import pytest

from app.extensions import db
from app.rpa.workers import gasca_sms_worker as worker


@pytest.mark.parametrize("enabled,customer_waiting,expected_pulse", [
    ("false", False, False),
    ("true", False, True),
    ("true", True, False),
])
def test_worker_never_sends_parallel_control_sms(
    monkeypatch, enabled, customer_waiting, expected_pulse,
):
    fake_app = Flask(__name__)
    fake_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    db.init_app(fake_app)
    monkeypatch.setenv("GASCA_SMS_PULSE_ENABLED", enabled)
    monkeypatch.setenv("GASCA_SMS_PULSE_PHONE", "5555555555")
    monkeypatch.setattr(worker, "_shutdown_requested", False)

    def one_iteration(_duration):
        monkeypatch.setattr(worker, "_shutdown_requested", True)

    request = SimpleNamespace(
        id=17, pin_normalized="12345", requested_phone_masked="***5555", status="sent"
    )
    session = MagicMock()
    with (
        patch.object(worker, "create_app", return_value=fake_app),
        patch.object(worker, "_install_signal_handlers"),
        patch.object(worker, "_report_worker_health"),
        patch.object(worker, "_claim_next_pending_request",
                     return_value=request if customer_waiting else None),
        patch.object(worker, "_has_pending_requests", return_value=False),
        patch.object(worker, "reserve_pulse", return_value=42) as reserve,
        patch.object(worker, "finish_pulse") as finish,
        patch.object(worker, "GoogleMessagesSmsSenderSession", return_value=session),
        patch.object(worker, "process_gasca_sms_request") as commercial,
        patch.object(worker.time, "sleep", side_effect=one_iteration),
    ):
        worker.run_worker_loop()

    if expected_pulse:
        reserve.assert_called_once()
        assert session.send.call_count == 1
        phone, message = session.send.call_args.args
        assert phone == "5555555555"
        assert "42" in message
        finish.assert_called_once_with(42, sent=True)
        commercial.assert_not_called()
    else:
        reserve.assert_not_called()
        session.send.assert_not_called()
        if customer_waiting:
            commercial.assert_called_once()
