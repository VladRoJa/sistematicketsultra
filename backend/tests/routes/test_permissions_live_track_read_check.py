"""Una casilla Track debe afectar HTTP real, conservando guard de procesos.

Todos los usuarios/grants son sintéticos. Sin red ni PostgreSQL productivo.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import track_routes as track


def _client(*, enabled=True):
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="qa-track-action-checkbox",
                      PERMISSIONS_TRACK_READ_GRANTS_ENABLED=enabled)
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


@pytest.mark.parametrize("role,effect,expected", [
    ("GERENTE", "deny", False),
    ("RECEPCIONISTA", "allow", True),
])
def test_track_matrix_matches_real_global_grant(role, effect, expected):
    from app.routes import permissions_visual_audit_routes as visual

    user = SimpleNamespace(
        id=47, username="QA", rol=role,
        sucursal_id=1, sucursales_ids=[1], department_id=1,
    )
    action = SimpleNamespace(
        id=10, full_key="track.read", name="Consultar Track", is_active=True,
        module=SimpleNamespace(id=3, key="track", name="Track", base_action_id=10),
    )
    grant = SimpleNamespace(
        id=39, action_id=10, effect=effect, scope_type="global",
        scope_branch_id=None, scope_branch_ids=[],
        scope_department_id=None, scope_payload=None,
        starts_at=None, expires_at=None,
        reason="QA de lectura Track",
    )
    context = {
        "user": user, "role": role, "sucursal_ids": [1],
        "warehouse_operator": None, "planning_operator": None,
        "allow_ticket_delete_all": False, "pm_scoped_read": False,
    }
    # La matriz no califica un grant como operativo con el flag apagado.
    app = Flask(__name__)
    app.config["PERMISSIONS_TRACK_READ_GRANTS_ENABLED"] = True
    with app.app_context():
        row = visual.evaluate_pair(
            user, action, context, {(10, "user", 47): grant},
        )
    assert row["legacy_allowed"] is expected
    assert row["catalog_allowed"] is expected
    assert row["comparison"] == "coincide"
    assert row["legacy_source"] == "track._require_track_read_role+grant"


def test_track_read_gate_off_preserves_legacy_no_extra_db(monkeypatch):
    client, headers = _client(enabled=False)
    monkeypatch.setattr(track, "_get_current_role", lambda: "GERENTE")
    monkeypatch.setattr(
        track.UserORM, "get_by_id",
        lambda _id: pytest.fail("No debe consultar Usuario/ORM si flag OFF"),
    )
    with patch.object(track, "resolve_effective_track_daily_version", return_value=None):
        response = client.get(
            "/api/track/daily-mart?track_date=2026-10-28",
            headers=headers,
        )
    assert response.status_code == 200
    assert response.json["status"] == "ok"


def test_track_read_gate_default_is_off_without_setting():
    app = Flask(__name__)
    with app.app_context():
        assert track.track_read_grants_enabled() is False


def test_track_matrix_does_not_claim_http_grant_when_flag_off():
    from app.routes import permissions_visual_audit_routes as visual
    app = Flask(__name__)
    app.config["PERMISSIONS_TRACK_READ_GRANTS_ENABLED"] = False
    user = SimpleNamespace(
        id=47, username="QA", rol="GERENTE",
        sucursal_id=1, sucursales_ids=[1], department_id=1,
    )
    action = SimpleNamespace(
        id=10, full_key="track.read", name="Consultar Track", is_active=True,
        module=SimpleNamespace(id=3, key="track", name="Track", base_action_id=10),
    )
    grant = SimpleNamespace(
        id=20, action_id=10, effect="deny", reason="configuracion anterior",
        scope_type="global", scope_branch_id=None, scope_branch_ids=[],
        scope_department_id=None, scope_payload=None,
        starts_at=None, expires_at=None,
    )
    context = {
        "user": user, "role": "GERENTE", "sucursal_ids": [1],
        "warehouse_operator": None, "planning_operator": None,
        "allow_ticket_delete_all": False, "pm_scoped_read": False,
    }
    with app.app_context():
        row = visual.evaluate_pair(user, action, context, {(10, "user", 47): grant})
    assert row["legacy_allowed"] is True
    assert row["catalog_allowed"] is False
    assert row["comparison"] == "diferencia"
    assert row["catalog_source"] == "grant_diagnostico_no_enforcement"
