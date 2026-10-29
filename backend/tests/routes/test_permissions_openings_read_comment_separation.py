"""Aperturas: check de consulta no autoriza comentarios ni otros POST.

Validación sintética de guards, sin DB ni escrituras productivas.
"""
from unittest.mock import patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import openings_routes as openings


@pytest.mark.parametrize("role,allowed", [
    ("APERTURAS_ADMIN", True),
    ("APERTURAS_COLABORADOR", True),
    ("APERTURAS_LECTOR", True),
    ("GERENTE_REGIONAL", True),
    ("RECEPCIONISTA", False),
])
def test_comment_guard_preserves_legacy_read_role_access(role, allowed):
    app = Flask(__name__)
    with app.app_context(), patch.object(openings, "_current_role", return_value=role):
        result = openings._require_openings_comment()
    assert (result is None) is allowed
    if result is not None:
        assert result[1] == 403


def test_read_guard_does_not_authorize_comment_creation():
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="synthetic-openings-separation")
    JWTManager(app)
    app.register_blueprint(openings.openings_bp, url_prefix="/api/openings")
    with app.app_context():
        token = create_access_token(identity="77")
    # Simula que un futuro grant permite lectura; comentario debe mantener
    # su propio guard, antes de cualquier consulta o mutación de DB.
    with patch.object(openings, "_require_openings_read", return_value=None), \
         patch.object(openings, "_current_role", return_value="RECEPCIONISTA"), \
         patch.object(openings.db.session, "add") as add:
        response = app.test_client().post(
            "/api/openings/1/tasks/2/comments",
            headers={"Authorization": "Bearer " + token},
            json={"comment": "No permitido por un check de lectura"},
        )
    assert response.status_code == 403
    add.assert_not_called()


def test_create_comment_requires_jwt_even_if_role_is_allowed():
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="synthetic-openings-jwt")
    JWTManager(app)
    app.register_blueprint(openings.openings_bp, url_prefix="/api/openings")
    with patch.object(openings, "_current_role", return_value="APERTURAS_ADMIN"):
        response = app.test_client().post(
            "/api/openings/1/tasks/2/comments", json={"comment": "No JWT"},
        )
    assert response.status_code == 401


@pytest.mark.parametrize("role,override,expected_status", [
    ("APERTURAS_ADMIN", None, 200),
    ("RECEPCIONISTA", None, 403),
    ("APERTURAS_COLABORADOR", False, 403),
    ("RECEPCIONISTA", True, 200),
])
def test_openings_read_check_changes_actual_http_guard(role, override, expected_status):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="synthetic-openings-read",
        PERMISSIONS_OPENINGS_READ_GRANTS_ENABLED=True,
    )
    JWTManager(app)

    @app.get("/protected-openings-read")
    @jwt_required()
    def protected():
        denied = openings._require_openings_read()
        return denied if denied is not None else {"ok": True}, 200

    with app.app_context():
        token = create_access_token(identity="77")
    with patch.object(openings, "_current_role", return_value=role), \
         patch.object(openings, "_openings_read_override", return_value=override):
        response = app.test_client().get(
            "/protected-openings-read",
            headers={"Authorization": "Bearer " + token},
        )
    assert response.status_code == expected_status


def test_openings_read_flag_off_does_not_consult_extra_grants():
    app = Flask(__name__)
    app.config["PERMISSIONS_OPENINGS_READ_GRANTS_ENABLED"] = False
    with app.test_request_context("/api/openings"):
        with patch.object(openings.UserORM, "get_by_id") as lookup:
            assert openings._openings_read_override() is None
            lookup.assert_not_called()


def test_openings_read_flag_off_is_default():
    app = Flask(__name__)
    with app.app_context():
        assert openings.openings_read_grants_enabled() is False


def test_openings_read_grant_on_does_not_open_comment_route():
    app = Flask(__name__)
    app.config.update(
        TESTING=True, JWT_SECRET_KEY="synthetic-openings-isolation",
        PERMISSIONS_OPENINGS_READ_GRANTS_ENABLED=True,
    )
    JWTManager(app)
    app.register_blueprint(openings.openings_bp, url_prefix="/api/openings")
    with app.app_context():
        token = create_access_token(identity="77")
    with patch.object(openings, "_openings_read_override", return_value=True), \
         patch.object(openings, "_current_role", return_value="RECEPCIONISTA"), \
         patch.object(openings.db.session, "add") as write:
        result = app.test_client().post(
            "/api/openings/1/tasks/1/comments",
            headers={"Authorization": "Bearer " + token},
            json={"comment": "No crear con permiso de lectura"},
        )
    assert result.status_code == 403
    write.assert_not_called()


def test_openings_module_writer_rejects_while_flag_off(monkeypatch):
    from types import SimpleNamespace
    from app.routes import permissions_catalog_routes as catalog

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="synthetic-openings-writer",
        PERMISSIONS_OPENINGS_READ_GRANTS_ENABLED=False,
    )
    JWTManager(app)
    app.register_blueprint(
        catalog.permissions_catalog_bp,
        url_prefix="/api/permissions/catalog",
    )
    with app.app_context():
        token = create_access_token(identity="47")
    monkeypatch.setattr(
        catalog, "_current_admin_user_or_error",
        lambda: (SimpleNamespace(id=47), None),
    )
    class TargetQuery:
        @staticmethod
        def get(user_id):
            return SimpleNamespace(id=user_id)
    monkeypatch.setattr(catalog, "UserORM", SimpleNamespace(query=TargetQuery()))
    result = app.test_client().put(
        "/api/permissions/catalog/users/99/module-access",
        headers={"Authorization": "Bearer " + token},
        json={"changes": [{
            "module_key": "openings", "override": "allow",
            "reason": "Intento guardado no autorizado en apertura",
        }]},
    )
    assert result.status_code == 409
    assert result.json["module_key"] == "openings"
