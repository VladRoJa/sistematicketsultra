from unittest.mock import patch

import pytest
import werkzeug
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.track_alerts.routes.track_alert_routes import track_alert_bp
from app.warehouse.services.track_forecast_center_service import (
    ForecastCenterAuthorizationError,
)


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

    user = object()

    with patch(
        "app.track_alerts.routes.track_alert_routes._require_track_read_role",
    ), patch(
        "app.track_alerts.routes.track_alert_routes._get_current_track_alert_user",
        return_value=user,
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
    assert get_operational.call_args.kwargs["user"] is user
    assert get_operational.call_args.kwargs["generation_mode"] == (
        "manual_preview"
    )


def test_branch_operational_detail_requires_jwt(client_and_token):
    client, _ = client_and_token

    response = client.get(
        "/api/track-alerts/branch-operational-detail",
        query_string={
            "sucursal_canon": "SALTILLO_VILLALTA",
            "track_date": "2026-08-19",
        },
    )

    assert response.status_code == 401


def test_branch_operational_detail_rejects_missing_branch(client_and_token):
    client, token = client_and_token

    with patch(
        "app.track_alerts.routes.track_alert_routes._require_track_read_role",
    ):
        response = client.get(
            "/api/track-alerts/branch-operational-detail",
            query_string={"track_date": "2026-08-19"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 400
    assert response.get_json()["error"] == "sucursal_canon es requerido."


def test_branch_operational_detail_dispatches_authorized_user(client_and_token):
    client, token = client_and_token
    user = object()
    expected = {
        "status": "ok",
        "identity": {"sucursal_canon": "SALTILLO_VILLALTA"},
    }

    with patch(
        "app.track_alerts.routes.track_alert_routes._require_track_read_role",
    ), patch(
        "app.track_alerts.routes.track_alert_routes._get_current_track_alert_user",
        return_value=user,
    ), patch(
        "app.track_alerts.routes.track_alert_routes.get_track_branch_operational_detail",
        return_value=expected,
    ) as get_detail:
        response = client.get(
            "/api/track-alerts/branch-operational-detail",
            query_string={
                "sucursal_canon": "saltillo_villalta",
                "track_date": "2026-08-19",
                "generation_mode": "manual_preview",
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.get_json() == expected
    assert get_detail.call_args.kwargs["user"] is user
    assert get_detail.call_args.kwargs["sucursal_canon"] == "saltillo_villalta"


def test_branch_operational_detail_scope_manipulation_is_403(client_and_token):
    client, token = client_and_token

    with patch(
        "app.track_alerts.routes.track_alert_routes._require_track_read_role",
    ), patch(
        "app.track_alerts.routes.track_alert_routes._get_current_track_alert_user",
        return_value=object(),
    ), patch(
        "app.track_alerts.routes.track_alert_routes.get_track_branch_operational_detail",
        side_effect=ForecastCenterAuthorizationError(
            "Sucursal fuera del alcance autorizado."
        ),
    ):
        response = client.get(
            "/api/track-alerts/branch-operational-detail",
            query_string={
                "sucursal_canon": "SALTILLO_VILLALTA",
                "track_date": "2026-08-19",
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 403
    assert response.get_json()["error"] == (
        "Sucursal fuera del alcance autorizado."
    )
