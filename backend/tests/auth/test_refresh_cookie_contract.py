"""Contrato RED: el login debe crear una credencial de renovación protegida.

Este test es deliberadamente fallido hasta que el backend implemente
renovación rotativa de sesión. No debe integrarse solo a main.
"""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask
from flask_jwt_extended import JWTManager

from app.routes.auth_routes import auth_bp


def test_login_emite_cookie_refresh_segura_sin_romper_respuesta_actual():
    """El JWT de acceso sigue en JSON; la credencial refresh solo en cookie."""
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="refresh-cookie-contract-test-only",
        JWT_ACCESS_TOKEN_EXPIRES=timedelta(minutes=45),
    )
    JWTManager(app)
    app.register_blueprint(auth_bp, url_prefix="/api/auth")

    user = SimpleNamespace(
        id=47,
        username="usuario_contrato",
        rol="ADMINISTRADOR",
        sucursal_id=1000,
        sucursales_ids=[1000],
        department_id=1000,
        verify_password=lambda value: value == "password-solo-prueba",
    )

    with patch(
        "app.routes.auth_routes.UserORM.get_by_username",
        return_value=user,
    ):
        response = app.test_client().post(
            "/api/auth/login",
            json={
                "username": "usuario_contrato",
                "password": "password-solo-prueba",
            },
            base_url="https://suiteultragym.com",
            headers={"Origin": "https://suiteultragym.com"},
        )

    assert response.status_code == 200
    payload = response.get_json()
    assert isinstance(payload.get("token"), str) and payload["token"]
    assert payload["user"]["id"] == 47
    assert "refresh_token" not in payload

    refresh_cookie = next(
        (
            header
            for header in response.headers.getlist("Set-Cookie")
            if header.startswith("suite_refresh=")
        ),
        None,
    )
    assert refresh_cookie is not None, (
        "RED esperado: login todavía no emite suite_refresh; "
        "implementar renovación segura antes de integrar este test."
    )

    attributes = {
        piece.strip().lower()
        for piece in refresh_cookie.split(";")[1:]
    }
    assert "httponly" in attributes
    assert "secure" in attributes
    assert ("samesite=lax" in attributes or "samesite=strict" in attributes)
    assert "path=/api/auth" in attributes
