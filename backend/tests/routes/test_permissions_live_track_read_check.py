"""Una casilla Track debe afectar HTTP real, conservando guard de procesos.

Todos los usuarios/grants son sintéticos. Sin red ni PostgreSQL productivo.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import track_routes as track


def _client():
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="qa-track-action-checkbox")
    JWTManager(app)
    app.register_blueprint(track.track_bp, url_prefix="/api/track")
    with app.app_context():
        token = create_access_token(identity="47")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("role,override,code", [
    ("GERENTE", None, 200),      # sin grant, rol legacy igual que antes
    ("RECEPCIONISTA", None, 403),
    ("GERENTE", False, 403),     # check deshabilitado: 403 efectivo
    ("RECEPCIONISTA", True, 200),# check habilitado: lectura real
])
def test_track_read_checkbox_changes_daily_mart_http(monkeypatch, role, override, code):
    client, headers = _client()
    monkeypatch.setattr(track, "_get_current_role", lambda: role)
    monkeypatch.setattr(track, "_track_read_user_override", lambda: override)
    with patch.object(track, "resolve_effective_track_daily_version", return_value=None):
        result = client.get(
            "/api/track/daily-mart?track_date=2026-10-28",
            headers=headers,
        )
    assert result.status_code == code
    assert result.json["status"] == ("ok" if code == 200 else "error")


def test_track_read_keeps_pipeline_admin_guard_independent(monkeypatch):
    monkeypatch.setattr(track, "_get_current_role", lambda: "GERENTE")
    monkeypatch.setattr(track, "_track_read_user_override", lambda: True)
    assert track._require_track_read_role() is None
    with pytest.raises(PermissionError, match="ejecutar procesos"):
        track._require_track_admin_role()


def test_track_read_falls_back_to_existing_roles_without_request(monkeypatch):
    monkeypatch.setattr(track, "_get_current_role", lambda: "GERENTE")
    assert track._track_read_user_override() is None
    assert track._require_track_read_role() is None


def test_track_grant_selection_user_before_role(monkeypatch):
    from app.models.permissions import PermissionActionORM
    from app.routes import permissions_catalog_routes as catalog

    client, headers = _client()
    # La consulta del actor se realiza sobre identity DB, no claims del frontend.
    fake_user = SimpleNamespace(id=47, rol="GERENTE")
    monkeypatch.setattr(track.UserORM, "get_by_id", lambda user_id: fake_user)
    class FakeActionQuery:
        def filter_by(self, **kwargs):
            assert kwargs == {"full_key": "track.read", "is_active": True}
            return self
        def first(self):
            return SimpleNamespace(id=9)

    # El descriptor ORM necesita application context aun cuando está mockeado.
    app = client.application
    with app.app_context():
        monkeypatch.setattr(PermissionActionORM, "query", FakeActionQuery(), raising=False)
        def read_grants(*, user, action_ids):
            assert user.id == 47 and action_ids == [9]
            return {
                "user": {9: SimpleNamespace(effect="deny")},
                "role": {9: SimpleNamespace(effect="allow")},
            }
        monkeypatch.setattr(catalog, "_get_latest_active_grants_by_action", read_grants)
        # Endpoint real de lectura Track utiliza _track_read_user_override.
        result = client.get(
            "/api/track/daily-mart?track_date=2026-10-28",
            headers=headers,
        )
    assert result.status_code == 403
    assert "No autorizado" in result.json["message"]


def test_track_read_missing_jwt_still_401_even_if_grant_would_allow(monkeypatch):
    client, _ = _client()
    monkeypatch.setattr(track, "_track_read_user_override", lambda: True)
    response = client.get("/api/track/daily-mart?track_date=2026-10-28")
    assert response.status_code == 401
