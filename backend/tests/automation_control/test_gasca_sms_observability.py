"""SMS Gasca: evidencia real y diagnósticos sin información sensible."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.extensions import db
from app.models.rpa import GascaSmsRequestORM
from app.rpa.services.gasca_sms_request_service import _is_explicit_session_gate_error
from app.rpa.services.google_messages_sms_sender_service import GoogleMessagesSmsSenderError
from app.services.automation_control.diagnostic_service import _safe_response
from app.services.automation_control.job_read_service import (
    _serialize_gasca_sms_request, list_job_runs,
)
from app.routes.automation_control_routes import automation_control_bp


STAMP = datetime(2026, 10, 20, 20, 0, tzinfo=timezone.utc)


def _sample_request(status="failed"):
    return SimpleNamespace(
        id=505, status=status, created_at=STAMP, last_attempt_at=STAMP,
        processed_at=STAMP, sent_at=None, attempt_count=2,
        internal_error="SECRET_PHONE_6861234567 SECRET_CODE_123456",
        pin_raw="12345", requested_phone_raw="6861234567",
        gasca_code_masked="***456",
    )


def test_domain_history_has_no_phone_pin_code_or_raw_error():
    row = _sample_request()
    data = _serialize_gasca_sms_request(row)
    assert data["run_id"] == 505
    assert data["status_raw"] == "failed"
    assert data["business_date"] is None
    assert data["counts"]["attempts"] == 2
    assert data["evidence_type"] == "SMS_REQUEST"
    assert all(secret not in str(data) for secret in (
        "6861234567", "123456", "12345", "SECRET_PHONE", "SECRET_CODE"
    ))


def test_unverified_sms_error_is_never_echoed_in_diagnostic():
    row = GascaSmsRequestORM(
        id=505,
        status="failed",
        last_attempt_at=STAMP,
        processed_at=STAMP,
        internal_error="SECRET_PHONE_6861234567 SECRET_CODE_123456",
    )
    data = _safe_response("gasca.sms_dispatch", row)
    assert data["diagnostic_state"] == "LOG_NOT_AVAILABLE"
    assert data["business_date"] is None
    assert data["run_id"] == 505
    assert not data["log_lines"]
    assert "6861234567" not in str(data)
    assert "123456" not in str(data)


def test_sms_history_paginates_by_real_request_rows():
    q = MagicMock()
    for method in ("filter", "order_by", "offset", "limit"):
        getattr(q, method).return_value = q
    q.all.return_value = [_sample_request("sent"), _sample_request("pending")]
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    db.init_app(app)
    with app.app_context():
        with patch.object(GascaSmsRequestORM, "query", q):
            data = list_job_runs("gasca.sms_dispatch", limit=1, offset=3)
    assert data["coverage"] == "DOMAIN_RUNS"
    assert data["has_more"] is True
    assert len(data["rows"]) == 1
    assert data["rows"][0]["status_raw"] == "sent"
    q.offset.assert_called_once_with(3)
    q.limit.assert_called_once_with(2)


def test_telemetry_endpoint_is_read_only_jwt_and_admicorp():
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="test-sms-observability")
    JWTManager(app)
    app.register_blueprint(automation_control_bp, url_prefix="/api/automation-control")
    client = app.test_client()
    url = "/api/automation-control/sms-gasca/queue"
    assert client.get(url).status_code == 401
    with app.app_context():
        token = create_access_token(identity="47")
    headers = {"Authorization": f"Bearer {token}"}
    with patch("app.routes.automation_control_routes._require_read_access", return_value=False):
        assert client.get(url, headers=headers).status_code == 403
    payload = {"pending": 1, "in_progress": 0, "sent_last_24h": 3,
               "failed_last_24h": 1, "session_status": "UNVERIFIED"}
    with (
        patch("app.routes.automation_control_routes._require_read_access", return_value=True),
        patch("app.routes.automation_control_routes.read_gasca_sms_queue", return_value=payload),
    ):
        result = client.get(url, headers=headers)
    assert result.status_code == 200
    assert result.get_json()["session_status"] == "UNVERIFIED"
    assert result.get_json()["pending"] == 1
    assert client.post(url, headers=headers).status_code == 405


def test_only_explicit_google_messages_login_gates_require_pairing():
    assert _is_explicit_session_gate_error(GoogleMessagesSmsSenderError(
        "Google Messages requiere iniciar sesión en Google. No se envió SMS."
    ))
    assert _is_explicit_session_gate_error(GoogleMessagesSmsSenderError(
        "Google Messages sigue en pantalla de bienvenida. No se envió SMS."
    ))
    assert not _is_explicit_session_gate_error(GoogleMessagesSmsSenderError(
        "Google Messages no confirmó el envío; no afirmar sesión caída."
    ))
