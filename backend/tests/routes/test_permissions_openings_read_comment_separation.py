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
