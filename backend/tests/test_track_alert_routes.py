from unittest.mock import patch

import pytest
import werkzeug
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.track_alerts.routes.track_alert_routes import track_alert_bp


@pytest.fixture
def client_and_token(monkeypatch):
    monkeypatch.setattr(
        werkzeug,
        "__version__",
        "3.1.3",
        raising=False,
    )
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="track-alert-test-secret",
    )
    JWTManager(app)
    app.register_blueprint(track_alert_bp)

    with app.app_context():
        token = create_access_token(identity="1")

    return app.test_client(), token


def test_regional_detail_requires_jwt(client_and_token):
    client, _ = client_and_token

    response = client.get(
        "/api/track-alerts/regional-detail",
        query_string={"track_date": "2026-08-17"},
    )

    assert response.status_code == 401


def test_regional_detail_enforces_track_read_permission(client_and_token):
    client, token = client_and_token

    with patch(
        "app.track_alerts.routes.track_alert_routes._require_track_read_role",
        side_effect=PermissionError("No autorizado para consultar el Track."),
    ):
        response = client.get(
            "/api/track-alerts/regional-detail",
            query_string={"track_date": "2026-08-17"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 403
    assert response.get_json()["error"] == (
        "No autorizado para consultar el Track."
    )


def test_regional_detail_dispatches_operational_view(client_and_token):
    client, token = client_and_token
    expected = {
        "track_date": "2026-08-17",
        "generation_mode": "manual_preview",
        "resolved_version": None,
        "regions": [],
        "priorities": [],
        "business_rules": [],
    }

    with patch(
        "app.track_alerts.routes.track_alert_routes._require_track_read_role",
    ), patch(
        "app.track_alerts.routes.track_alert_routes.get_regional_operational_detail",
        return_value=expected,
    ) as get_operational:
        response = client.get(
            "/api/track-alerts/regional-detail",
            query_string={
                "track_date": "2026-08-17",
                "generation_mode": "manual_preview",
                "view": "operational",
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.get_json() == expected
    get_operational.assert_called_once()
    assert get_operational.call_args.kwargs["generation_mode"] == (
        "manual_preview"
    )
