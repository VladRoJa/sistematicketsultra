"""P29 regression: unauthenticated calls cannot generate/send Track alerts.

Synthetic Flask/JWT, service/DB/SMTP mocked: no providers or production data.
Also protects the deliberate internal-token exception for Warehouse jobs.
"""
from unittest.mock import patch

import pytest
import werkzeug
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.track_alerts.routes.track_alert_routes import track_alert_bp
from app.routes.warehouse_internal_jobs import warehouse_internal_jobs_bp


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(werkzeug, "__version__", "3.1.3", raising=False)
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="p29-track-alert-synthetic")
    JWTManager(app)
    app.register_blueprint(track_alert_bp)
    with app.app_context():
        token = create_access_token(identity="7")
    return app.test_client(), {"Authorization": "Bearer " + token}


@pytest.mark.parametrize("method,path", [
    ("POST", "/api/track-alerts/test"),
    ("POST", "/api/track-alerts/generate"),
    ("POST", "/api/track-alerts/regional-test"),
    ("POST", "/api/track-alerts/send-email"),
    ("POST", "/api/track-alerts/send-regional-email"),
    ("GET", "/api/track-alerts/preview-email"),
    ("GET", "/api/track-alerts/regional-preview-email"),
])
def test_all_seven_alert_routes_reject_missing_jwt_before_payload(api, method, path):
    client, _ = api
    response = client.open(path, method=method, json={"track_date": "2026-10-26"}
                           if method == "POST" else None)
    assert response.status_code == 401


@pytest.mark.parametrize("path", [
    "/api/track-alerts/test",
    "/api/track-alerts/generate",
    "/api/track-alerts/regional-test",
    "/api/track-alerts/send-email",
    "/api/track-alerts/send-regional-email",
])
def test_unauthorized_role_rejected_before_preview_or_send_service(api, path):
    client, auth = api
    with patch("app.routes.track_routes._get_current_role", return_value="RECEPCIONISTA"), \
         patch("app.track_alerts.routes.track_alert_routes.generate_track_alert_events") as generate, \
         patch("app.track_alerts.routes.track_alert_routes.evaluate_track_alerts") as evaluate, \
         patch("app.track_alerts.routes.track_alert_routes.send_executive_track_alert_email") as send, \
         patch("app.track_alerts.routes.track_alert_routes.send_regional_executive_track_alert_email") as send_regional, \
         patch("app.track_alerts.routes.track_alert_routes.evaluate_regional_rankings") as region:
        response = client.post(
            path,
            json={"track_date": "2026-10-26", "to_list": ["qa@example.invalid"]},
            headers=auth,
        )
    assert response.status_code == 403
    for service in (generate, evaluate, send, send_regional, region):
        service.assert_not_called()


@pytest.mark.parametrize("path,service_name", [
    ("/api/track-alerts/generate", "generate_track_alert_events"),
    ("/api/track-alerts/send-email", "send_executive_track_alert_email"),
    ("/api/track-alerts/send-regional-email", "send_regional_executive_track_alert_email"),
])
def test_track_reader_cannot_trigger_generation_or_email(api, path, service_name):
    client, auth = api
    with patch("app.routes.track_routes._get_current_role", return_value="GERENTE"), \
         patch("app.track_alerts.routes.track_alert_routes." + service_name) as effect:
        response = client.post(
            path,
            json={"track_date": "2026-10-26", "to_list": ["qa@example.invalid"]},
            headers=auth,
        )
    assert response.status_code == 403
    effect.assert_not_called()


@pytest.mark.parametrize("path", [
    "/api/track-alerts/preview-email",
    "/api/track-alerts/regional-preview-email",
])
def test_preview_email_requires_track_read_role(api, path):
    client, auth = api
    with patch("app.routes.track_routes._get_current_role", return_value="RECEPCIONISTA"):
        response = client.get(path, query_string={"track_date": "2026-10-26"}, headers=auth)
    assert response.status_code == 403


def test_track_manager_still_can_run_readonly_manual_preview(api):
    client, auth = api
    with patch("app.routes.track_routes._get_current_role", return_value="GERENTE"), \
         patch("app.track_alerts.routes.track_alert_routes.evaluate_track_alerts", return_value=[]) as preview:
        response = client.post(
            "/api/track-alerts/test",
            json={"track_date": "2026-10-26"},
            headers=auth,
        )
    assert response.status_code == 200
    preview.assert_called_once()


def test_track_admin_can_generate_events_with_mocked_service(api):
    client, auth = api
    with patch("app.routes.track_routes._get_current_role", return_value="ADMINISTRADOR"), \
         patch("app.track_alerts.routes.track_alert_routes.generate_track_alert_events",
               return_value={"generated": 1}) as generate:
        response = client.post(
            "/api/track-alerts/generate",
            json={"track_date": "2026-10-26"},
            headers=auth,
        )
    assert response.status_code == 200
    assert response.get_json()["generated"] == 1
    generate.assert_called_once()


def test_warehouse_internal_job_uses_independent_token_not_jwt(monkeypatch):
    app = Flask(__name__)
    app.config.update(TESTING=True, WAREHOUSE_INTERNAL_JOBS_TOKEN="synthetic-internal-secret")
    app.register_blueprint(warehouse_internal_jobs_bp, url_prefix="/api/warehouse/internal")
    client = app.test_client()
    payload = {"report_type_key": "reporte_direccion", "run_mode": "scheduled_daily"}
    with patch("app.routes.warehouse_internal_jobs._call_orchestrator") as effect:
        response = client.post("/api/warehouse/internal/gasca-report-jobs", json=payload)
        assert response.status_code == 403
        effect.assert_not_called()
        response = client.post(
            "/api/warehouse/internal/gasca-report-jobs",
            json=payload,
            headers={"X-Suite-Internal-Token": "wrong-secret"},
        )
        assert response.status_code == 403
        effect.assert_not_called()
